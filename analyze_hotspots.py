from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer


ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "data_clean"
GEO = ROOT / "geo"
ANALYSIS = ROOT / "analysis"
MAPS = ROOT / "maps"

ANALYSIS.mkdir(exist_ok=True)
MAPS.mkdir(exist_ok=True)


# ============================================================
# 1. 공통 함수
# ============================================================

def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(
        CLEAN / name,
        encoding="utf-8-sig",
        low_memory=False,
    )


with open(GEO / "yuseong_boundary.geojson", encoding="utf-8") as f:
    boundary_fc = json.load(f)

geometry = boundary_fc["features"][0]["geometry"]


def polygon_rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]

    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]

    raise ValueError(
        f"Unsupported geometry: {geom['type']}"
    )


POLYGONS = polygon_rings(geometry)


def in_ring(lon: float, lat: float, ring) -> bool:
    inside = False
    j = len(ring) - 1

    for i in range(len(ring)):
        xi, yi = ring[i][:2]
        xj, yj = ring[j][:2]

        if (
            (yi > lat) != (yj > lat)
            and lon
            < (xj - xi)
            * (lat - yi)
            / ((yj - yi) or 1e-15)
            + xi
        ):
            inside = not inside

        j = i

    return inside


def in_boundary(lon: float, lat: float) -> bool:
    if not np.isfinite(lon) or not np.isfinite(lat):
        return False

    for polygon in POLYGONS:
        if not polygon:
            continue

        if (
            in_ring(lon, lat, polygon[0])
            and not any(
                in_ring(lon, lat, hole)
                for hole in polygon[1:]
            )
        ):
            return True

    return False


def clip_points(df: pd.DataFrame) -> pd.DataFrame:
    lon = pd.to_numeric(
        df["경도_WGS84"],
        errors="coerce",
    )

    lat = pd.to_numeric(
        df["위도_WGS84"],
        errors="coerce",
    )

    mask = [
        in_boundary(x, y)
        for x, y in zip(lon, lat)
    ]

    return df.loc[mask].copy()


def standardize_wgs84(
    df: pd.DataFrame,
    lon_candidates: list[str],
    lat_candidates: list[str],
) -> pd.DataFrame:

    result = df.copy()

    lon_col = next(
        (
            col
            for col in lon_candidates
            if col in result.columns
        ),
        None,
    )

    lat_col = next(
        (
            col
            for col in lat_candidates
            if col in result.columns
        ),
        None,
    )

    if lon_col is None or lat_col is None:
        raise KeyError(
            "경도/위도 좌표 열을 찾지 못했습니다.\n"
            f"현재 열: {list(result.columns)}"
        )

    result["경도_WGS84"] = pd.to_numeric(
        result[lon_col],
        errors="coerce",
    )

    result["위도_WGS84"] = pd.to_numeric(
        result[lat_col],
        errors="coerce",
    )

    return result


def minmax(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(
        series,
        errors="coerce",
    )

    lo = x.min()
    hi = x.max()

    if pd.isna(lo) or pd.isna(hi):
        return pd.Series(
            np.nan,
            index=x.index,
        )

    if hi == lo:
        return pd.Series(
            0.5,
            index=x.index,
        )

    return (x - lo) / (hi - lo)


# ============================================================
# 2. 최종 분석 데이터 불러오기
# ============================================================

# ------------------------------------------------------------
# CCTV
# ------------------------------------------------------------

cctv = load_csv(
    "01_cctv_clean.csv"
)

cctv = standardize_wgs84(
    cctv,
    lon_candidates=[
        "경도_WGS84",
        "longitude",
        "경도",
    ],
    lat_candidates=[
        "위도_WGS84",
        "latitude",
        "위도",
    ],
)

cctv = clip_points(cctv)


# ------------------------------------------------------------
# 가로등
# ------------------------------------------------------------

lights = load_csv(
    "02_streetlights_yuseong.csv"
)

lights = standardize_wgs84(
    lights,
    lon_candidates=[
        "경도_WGS84",
        "longitude",
        "경도",
    ],
    lat_candidates=[
        "위도_WGS84",
        "latitude",
        "위도",
    ],
)

lights = clip_points(lights)


# ------------------------------------------------------------
# 보안등
# ------------------------------------------------------------

security_lights = load_csv(
    "09_security_lights_yuseong.csv"
)

security_lights = standardize_wgs84(
    security_lights,
    lon_candidates=[
        "경도_WGS84",
        "longitude",
        "경도",
    ],
    lat_candidates=[
        "위도_WGS84",
        "latitude",
        "위도",
    ],
)

security_lights["설치개수"] = (
    pd.to_numeric(
        security_lights["설치개수"],
        errors="coerce",
    )
    .fillna(1)
    .clip(lower=1)
)

security_lights = clip_points(
    security_lights
)


# ------------------------------------------------------------
# 버스정류장
# 최종 정제된 정류장 위치 데이터 사용
# ------------------------------------------------------------

bus = load_csv(
    "12b_village_bus_stops_unique.csv"
)

bus = standardize_wgs84(
    bus,
    lon_candidates=[
        "경도",
        "경도_WGS84",
        "longitude",
    ],
    lat_candidates=[
        "위도",
        "위도_WGS84",
        "latitude",
    ],
)

bus = clip_points(bus)


# ------------------------------------------------------------
# 유성구청 제공 야간 유동인구
# 2025-08 ~ 2026-07
# 22:00 ~ 06:00
# ------------------------------------------------------------

population = load_csv(
    "14b_night_population_500m_period_average.csv"
)

for column in [
    "months_present",
    "avg_total_pop",
    "avg_source_coverage_pct",
    "center_x_epsg5179",
    "center_y_epsg5179",
]:
    population[column] = pd.to_numeric(
        population[column],
        errors="coerce",
    )


# 동일한 12개월 기간을 확보한 격자만
# 취약도 비교 대상으로 사용
population = population.loc[
    population["months_present"] == 12
].copy()


# EPSG:5179 → WGS84
to_wgs84 = Transformer.from_crs(
    "EPSG:5179",
    "EPSG:4326",
    always_xy=True,
)

pop_lon, pop_lat = to_wgs84.transform(
    population[
        "center_x_epsg5179"
    ].to_numpy(),
    population[
        "center_y_epsg5179"
    ].to_numpy(),
)

population["경도_WGS84"] = pop_lon
population["위도_WGS84"] = pop_lat

population = population.dropna(
    subset=[
        "경도_WGS84",
        "위도_WGS84",
        "avg_total_pop",
    ]
).copy()

population = clip_points(
    population
)


# ------------------------------------------------------------
# 경찰기관
# 취약도 산정에는 사용하지 않음
# 지도 및 후속 접근성 검증용
# ------------------------------------------------------------

police = load_csv(
    "08_police_stations_clean.csv"
)

police = standardize_wgs84(
    police,
    lon_candidates=[
        "longitude",
        "경도_WGS84",
        "경도",
    ],
    lat_candidates=[
        "latitude",
        "위도_WGS84",
        "위도",
    ],
)

police = clip_points(police)


# ============================================================
# 3. 500m 분석 격자 생성
# ============================================================

all_boundary_points = [
    pt
    for polygon in POLYGONS
    for ring in polygon
    for pt in ring
]

lons = np.array(
    [p[0] for p in all_boundary_points],
    dtype=float,
)

lats = np.array(
    [p[1] for p in all_boundary_points],
    dtype=float,
)

lon0 = float(lons.min())
lat0 = float(lats.min())

mx = (
    111_320
    * math.cos(
        math.radians(
            float(lats.mean())
        )
    )
)

my = 111_320

cell_size = 500.0


def add_cell(
    df: pd.DataFrame
) -> pd.DataFrame:

    result = df.copy()

    result["grid_x"] = np.floor(
        (
            pd.to_numeric(
                result["경도_WGS84"],
                errors="coerce",
            )
            - lon0
        )
        * mx
        / cell_size
    ).astype("Int64")

    result["grid_y"] = np.floor(
        (
            pd.to_numeric(
                result["위도_WGS84"],
                errors="coerce",
            )
            - lat0
        )
        * my
        / cell_size
    ).astype("Int64")

    return result


cctv_g = add_cell(cctv)
lights_g = add_cell(lights)
security_g = add_cell(security_lights)
bus_g = add_cell(bus)
population_g = add_cell(population)


max_x = math.ceil(
    (lons.max() - lon0)
    * mx
    / cell_size
)

max_y = math.ceil(
    (lats.max() - lat0)
    * my
    / cell_size
)


cells = []

for gx in range(max_x + 1):

    for gy in range(max_y + 1):

        center_lon = (
            lon0
            + (gx + 0.5)
            * cell_size
            / mx
        )

        center_lat = (
            lat0
            + (gy + 0.5)
            * cell_size
            / my
        )

        if in_boundary(
            center_lon,
            center_lat,
        ):

            sample_inside = 0
            sample_total = 25

            for sx in range(5):
                for sy in range(5):

                    sample_lon = (
                        lon0
                        + (
                            gx
                            + (sx + 0.5) / 5
                        )
                        * cell_size
                        / mx
                    )

                    sample_lat = (
                        lat0
                        + (
                            gy
                            + (sy + 0.5) / 5
                        )
                        * cell_size
                        / my
                    )

                    sample_inside += int(
                        in_boundary(
                            sample_lon,
                            sample_lat,
                        )
                    )

            cells.append(
                (
                    gx,
                    gy,
                    center_lon,
                    center_lat,
                    sample_inside
                    / sample_total,
                )
            )


grid = pd.DataFrame(
    cells,
    columns=[
        "grid_x",
        "grid_y",
        "중심경도",
        "중심위도",
        "경계포함비율",
    ],
)


# ============================================================
# 4. 각 격자에 시설·수요 데이터 결합
# ============================================================

def counts(
    frame: pd.DataFrame,
    name: str,
) -> pd.DataFrame:

    return (
        frame
        .dropna(
            subset=[
                "grid_x",
                "grid_y",
            ]
        )
        .groupby(
            [
                "grid_x",
                "grid_y",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size": name
            }
        )
    )


# CCTV
cctv_counts = counts(
    cctv_g,
    "CCTV수",
)

grid = grid.merge(
    cctv_counts,
    on=[
        "grid_x",
        "grid_y",
    ],
    how="left",
)

grid["CCTV수"] = (
    grid["CCTV수"]
    .fillna(0)
    .astype(int)
)


# 가로등
light_counts = counts(
    lights_g,
    "가로등수",
)

grid = grid.merge(
    light_counts,
    on=[
        "grid_x",
        "grid_y",
    ],
    how="left",
)

grid["가로등수"] = (
    grid["가로등수"]
    .fillna(0)
    .astype(int)
)


# 버스정류장
bus_counts = counts(
    bus_g,
    "버스정류장수",
)

grid = grid.merge(
    bus_counts,
    on=[
        "grid_x",
        "grid_y",
    ],
    how="left",
)

grid["버스정류장수"] = (
    grid["버스정류장수"]
    .fillna(0)
    .astype(int)
)


# 보안등은 단순 레코드 개수가 아니라
# 실제 설치개수 합계를 사용
security_counts = (
    security_g
    .dropna(
        subset=[
            "grid_x",
            "grid_y",
        ]
    )
    .groupby(
        [
            "grid_x",
            "grid_y",
        ],
        as_index=False,
    )["설치개수"]
    .sum()
    .rename(
        columns={
            "설치개수": "보안등수"
        }
    )
)

grid = grid.merge(
    security_counts,
    on=[
        "grid_x",
        "grid_y",
    ],
    how="left",
)

grid["보안등수"] = (
    grid["보안등수"]
    .fillna(0)
    .round()
    .astype(int)
)


# 가로등 + 보안등 = 조명시설
grid["조명시설수"] = (
    grid["가로등수"]
    + grid["보안등수"]
)


# ============================================================
# 5. 야간 유동인구 결합
# ============================================================

population_grid = (
    population_g
    .dropna(
        subset=[
            "grid_x",
            "grid_y",
        ]
    )
    .groupby(
        [
            "grid_x",
            "grid_y",
        ],
        as_index=False,
    )
    .agg(
        야간유동인구=(
            "avg_total_pop",
            "mean",
        ),
        유동인구개월수=(
            "months_present",
            "max",
        ),
        유동인구커버리지=(
            "avg_source_coverage_pct",
            "mean",
        ),
        유동인구원격자수=(
            "grid500_id",
            "nunique",
        ),
    )
)


grid = grid.merge(
    population_grid,
    on=[
        "grid_x",
        "grid_y",
    ],
    how="left",
)


# ============================================================
# 6. 분석 대상 격자 선정
# ============================================================

# 유동인구 데이터가 실제로 존재하면서
# 유성구 경계 안에 절반 이상 포함된 격자만 사용
grid["분석대상여부"] = (
    grid["야간유동인구"].notna()
    & (
        grid["경계포함비율"]
        >= 0.5
    )
)


eligible = grid.loc[
    grid["분석대상여부"]
].copy()


# ============================================================
# 7. 취약도 지표 정규화
# ============================================================

# 로그변환 + Min-Max 정규화
#
# 야간 유동인구와 버스정류장은
# 많을수록 안전관리 수요가 높다고 봄
eligible[
    "야간유동인구_정규화"
] = minmax(
    np.log1p(
        eligible["야간유동인구"]
    )
)

eligible[
    "버스수요_정규화"
] = minmax(
    np.log1p(
        eligible["버스정류장수"]
    )
)


# CCTV와 조명시설은
# 많을수록 시설공백이 작아짐
eligible[
    "CCTV부족_정규화"
] = (
    1
    - minmax(
        np.log1p(
            eligible["CCTV수"]
        )
    )
)

eligible[
    "조명시설부족_정규화"
] = (
    1
    - minmax(
        np.log1p(
            eligible["조명시설수"]
        )
    )
)


# ============================================================
# 8. 취약도 산정식
# ============================================================

# ------------------------------------------------------------
# 안전수요
#
# 야간 유동인구 60%
# 버스정류장 40%
# ------------------------------------------------------------

eligible[
    "안전수요점수"
] = (
    0.60
    * eligible[
        "야간유동인구_정규화"
    ]
    +
    0.40
    * eligible[
        "버스수요_정규화"
    ]
)


# ------------------------------------------------------------
# 시설공백
#
# CCTV 부족 55%
# 조명시설 부족 45%
#
# 조명시설 = 가로등 + 보안등
# ------------------------------------------------------------

eligible[
    "시설공백점수"
] = (
    0.55
    * eligible[
        "CCTV부족_정규화"
    ]
    +
    0.45
    * eligible[
        "조명시설부족_정규화"
    ]
)


# ------------------------------------------------------------
# 최종 취약도
#
# 안전수요 65%
# 시설공백 35%
# ------------------------------------------------------------

eligible[
    "격자취약도점수"
] = (
    (
        0.65
        * eligible[
            "안전수요점수"
        ]
    )
    +
    (
        0.35
        * eligible[
            "시설공백점수"
        ]
    )
) * 100


eligible[
    "격자취약도순위"
] = (
    eligible[
        "격자취약도점수"
    ]
    .rank(
        method="min",
        ascending=False,
    )
    .astype(int)
)


eligible = eligible.sort_values(
    [
        "격자취약도순위",
        "grid_y",
        "grid_x",
    ]
)


# ============================================================
# 9. 결과 저장
# ============================================================

eligible.to_csv(
    ANALYSIS
    / "03_grid_500m_hotspot_scores.csv",
    index=False,
    encoding="utf-8-sig",
)

eligible.head(30).to_csv(
    ANALYSIS
    / "04_top30_hotspots.csv",
    index=False,
    encoding="utf-8-sig",
)


# 기존 후속 코드와의 호환성을 위해
# 보완 버전 열 이름도 함께 생성
compatible = eligible.copy()

compatible[
    "시설공백점수_보완"
] = compatible[
    "시설공백점수"
]

compatible[
    "격자취약도점수_보완"
] = compatible[
    "격자취약도점수"
]

compatible[
    "격자취약도순위_보완"
] = compatible[
    "격자취약도순위"
]


compatible.to_csv(
    ANALYSIS
    / "07_grid_500m_hotspot_scores_with_security_lights.csv",
    index=False,
    encoding="utf-8-sig",
)

compatible.head(10).to_csv(
    ANALYSIS
    / "08_top10_hotspots_with_security_lights.csv",
    index=False,
    encoding="utf-8-sig",
)


# ============================================================
# 10. 취약지역 지도 생성
# ============================================================

with open(
    GEO / "yuseong_major_roads.geojson",
    encoding="utf-8",
) as f:
    roads = json.load(f)["features"]


W = 1500
H = 1500

map_left = 90
map_top = 190
map_right = 1410
map_bottom = 1370

lon_min = lons.min()
lon_max = lons.max()
lat_min = lats.min()
lat_max = lats.max()


def project(
    lon: float,
    lat: float,
):
    x = (
        map_left
        + (
            lon - lon_min
        )
        / (
            lon_max - lon_min
        )
        * (
            map_right
            - map_left
        )
    )

    y = (
        map_bottom
        - (
            lat - lat_min
        )
        / (
            lat_max - lat_min
        )
        * (
            map_bottom
            - map_top
        )
    )

    return x, y


img = Image.new(
    "RGB",
    (W, H),
    "white",
)

draw = ImageDraw.Draw(
    img,
    "RGBA",
)


font_path = (
    r"C:\Windows\Fonts\malgun.ttf"
)

bold_path = (
    r"C:\Windows\Fonts\malgunbd.ttf"
)


f_title = ImageFont.truetype(
    bold_path,
    46,
)

f_sub = ImageFont.truetype(
    font_path,
    24,
)

f_label = ImageFont.truetype(
    bold_path,
    23,
)

f_small = ImageFont.truetype(
    font_path,
    19,
)


draw.text(
    (80, 55),
    "유성구 야간 보행안전 취약지점 후보",
    font=f_title,
    fill="#222222",
)

draw.text(
    (82, 120),
    (
        "500m 격자 · 야간 유동인구·버스수요·"
        "안전시설 공백을 결합한 취약도 분석"
    ),
    font=f_sub,
    fill="#666666",
)


# ------------------------------------------------------------
# 유성구 경계
# ------------------------------------------------------------

for polygon in POLYGONS:

    outer = [
        project(*p[:2])
        for p in polygon[0]
    ]

    draw.polygon(
        outer,
        fill="#f3f6f9",
        outline="#4b5563",
        width=4,
    )


# ------------------------------------------------------------
# 주요 도로
# ------------------------------------------------------------

for feature in roads:

    coords = (
        feature[
            "geometry"
        ][
            "coordinates"
        ]
    )

    kind = (
        feature[
            "properties"
        ].get(
            "highway"
        )
    )

    if kind in {
        "motorway",
        "trunk",
    }:
        color = "#9ca3af"
        width = 3

    elif kind == "primary":
        color = "#cbd5e1"
        width = 2

    else:
        color = "#e2e8f0"
        width = 1

    pts = [
        project(*p[:2])
        for p in coords
    ]

    if len(pts) >= 2:
        draw.line(
            pts,
            fill=color,
            width=width,
        )


# ------------------------------------------------------------
# CCTV 표시
# ------------------------------------------------------------

for _, row in cctv.iterrows():

    x, y = project(
        float(
            row[
                "경도_WGS84"
            ]
        ),
        float(
            row[
                "위도_WGS84"
            ]
        ),
    )

    draw.ellipse(
        (
            x - 2,
            y - 2,
            x + 2,
            y + 2,
        ),
        fill="#2563eb",
    )


# ------------------------------------------------------------
# 경찰기관 표시
#
# 취약도 점수에는 포함하지 않고
# 후속 접근성 검토를 위한 참고시설로 표시
# ------------------------------------------------------------

for _, row in police.iterrows():

    x, y = project(
        float(
            row[
                "경도_WGS84"
            ]
        ),
        float(
            row[
                "위도_WGS84"
            ]
        ),
    )

    draw.regular_polygon(
        (
            x,
            y,
            8,
        ),
        4,
        rotation=45,
        fill="#111827",
    )


# ------------------------------------------------------------
# 취약도 상위 20개 격자
# ------------------------------------------------------------

top20 = eligible.head(20)

if not top20.empty:

    score_min = (
        top20[
            "격자취약도점수"
        ].min()
    )

    score_max = (
        top20[
            "격자취약도점수"
        ].max()
    )

    for idx, (_, row) in enumerate(
        top20.iterrows(),
        start=1,
    ):

        x, y = project(
            float(
                row[
                    "중심경도"
                ]
            ),
            float(
                row[
                    "중심위도"
                ]
            ),
        )

        norm = (
            row[
                "격자취약도점수"
            ]
            - score_min
        ) / (
            (
                score_max
                - score_min
            )
            or 1
        )

        radius = (
            13
            + 17
            * norm
        )

        draw.ellipse(
            (
                x - radius,
                y - radius,
                x + radius,
                y + radius,
            ),
            fill=(
                220,
                38,
                38,
                120,
            ),
            outline="#991b1b",
            width=2,
        )

        if idx <= 10:

            draw.text(
                (
                    x,
                    y,
                ),
                str(idx),
                font=f_label,
                fill="white",
                anchor="mm",
                stroke_width=2,
                stroke_fill="#991b1b",
            )


# ------------------------------------------------------------
# 범례
# ------------------------------------------------------------

legend_y = 1415


draw.ellipse(
    (
        90,
        legend_y - 8,
        106,
        legend_y + 8,
    ),
    fill=(
        220,
        38,
        38,
        150,
    ),
    outline="#991b1b",
)

draw.text(
    (
        118,
        legend_y,
    ),
    "취약지점 후보",
    font=f_small,
    fill="#333333",
    anchor="lm",
)


draw.ellipse(
    (
        330,
        legend_y - 3,
        336,
        legend_y + 3,
    ),
    fill="#2563eb",
)

draw.text(
    (
        348,
        legend_y,
    ),
    "CCTV",
    font=f_small,
    fill="#333333",
    anchor="lm",
)


draw.regular_polygon(
    (
        475,
        legend_y,
        7,
    ),
    4,
    rotation=45,
    fill="#111827",
)

draw.text(
    (
        490,
        legend_y,
    ),
    "경찰기관(참고)",
    font=f_small,
    fill="#333333",
    anchor="lm",
)


draw.text(
    (
        W - 85,
        legend_y,
    ),
    "경계·도로: OpenStreetMap",
    font=f_small,
    fill="#666666",
    anchor="rm",
)


img.save(
    MAPS
    / "01_yuseong_500m_hotspots.png"
)


# ============================================================
# 11. 실행 결과 확인
# ============================================================

print()
print("=" * 70)
print("유성구 야간 보행안전 취약도 분석 완료")
print("=" * 70)

print(
    f"CCTV: {len(cctv):,}건"
)

print(
    f"가로등: {len(lights):,}건"
)

print(
    "보안등 설치개수: "
    f"{int(security_lights['설치개수'].sum()):,}개"
)

print(
    f"버스정류장 위치: {len(bus):,}건"
)

print(
    "12개월 유동인구 원격자: "
    f"{len(population):,}개"
)

print(
    f"경찰기관: {len(police):,}곳"
)

print(
    f"전체 생성 격자: {len(grid):,}개"
)

print(
    f"최종 분석대상 격자: {len(eligible):,}개"
)

print()
print(
    "취약도 산정식:"
)

print(
    "안전수요 = "
    "0.60 × 야간유동인구 + "
    "0.40 × 버스정류장"
)

print(
    "시설공백 = "
    "0.55 × CCTV부족 + "
    "0.45 × 조명시설부족"
)

print(
    "취약도 = "
    "100 × (0.65 × 안전수요 + "
    "0.35 × 시설공백)"
)

print()
print("상위 10개 격자")
print("-" * 70)

print(
    eligible.head(10)[
        [
            "격자취약도순위",
            "중심경도",
            "중심위도",
            "격자취약도점수",
            "야간유동인구",
            "버스정류장수",
            "CCTV수",
            "가로등수",
            "보안등수",
            "조명시설수",
            "유동인구커버리지",
        ]
    ].to_string(
        index=False
    )
)