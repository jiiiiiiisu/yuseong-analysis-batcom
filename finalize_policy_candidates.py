from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "data_clean"
GEO = ROOT / "geo"
ANALYSIS = ROOT / "analysis"


# ============================================================
# 1. 공통 함수
# ============================================================

def load_clean(name: str) -> pd.DataFrame:
    return pd.read_csv(
        CLEAN / name,
        encoding="utf-8-sig",
        low_memory=False,
    )


def standardize_wgs84(
    df: pd.DataFrame,
    lon_candidates: list[str],
    lat_candidates: list[str],
) -> pd.DataFrame:
    """
    서로 다른 파일의 위경도 열 이름을
    경도_WGS84 / 위도_WGS84 로 통일한다.
    """
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
            "위경도 열을 찾지 못했습니다.\n"
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

    return result.dropna(
        subset=[
            "경도_WGS84",
            "위도_WGS84",
        ]
    ).copy()


def distances_m(
    lon: float,
    lat: float,
    frame: pd.DataFrame,
) -> np.ndarray:
    """
    후보지 중심점과 시설 간의 대략적인 직선거리(m)를 계산한다.
    """
    point_lon = pd.to_numeric(
        frame["경도_WGS84"],
        errors="coerce",
    ).to_numpy(float)

    point_lat = pd.to_numeric(
        frame["위도_WGS84"],
        errors="coerce",
    ).to_numpy(float)

    x = (
        (point_lon - lon)
        * 111_320
        * math.cos(math.radians(lat))
    )

    y = (
        (point_lat - lat)
        * 111_320
    )

    return np.sqrt(
        x * x + y * y
    )


def safe_min_distance(
    distances: np.ndarray,
) -> float:
    """
    시설이 없거나 유효한 거리가 없을 경우 NaN 반환.
    """
    valid = distances[
        np.isfinite(distances)
    ]

    if len(valid) == 0:
        return np.nan

    return float(
        valid.min()
    )


# ============================================================
# 2. 후보지역 이름용 도로망
# ============================================================

with open(
    GEO / "yuseong_major_roads.geojson",
    encoding="utf-8",
) as f:
    road_features = json.load(f)["features"]


def point_segment_distance_m(
    lon: float,
    lat: float,
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    """
    한 점과 도로 선분 사이의 근사 거리(m).
    유성구 범위의 소규모 거리 계산이므로
    지역 평면 근사를 사용한다.
    """
    cos_lat = math.cos(
        math.radians(lat)
    )

    x1 = (
        (lon1 - lon)
        * 111_320
        * cos_lat
    )

    y1 = (
        (lat1 - lat)
        * 111_320
    )

    x2 = (
        (lon2 - lon)
        * 111_320
        * cos_lat
    )

    y2 = (
        (lat2 - lat)
        * 111_320
    )

    dx = x2 - x1
    dy = y2 - y1

    denom = (
        dx * dx
        + dy * dy
    )

    if denom == 0:
        return math.sqrt(
            x1 * x1
            + y1 * y1
        )

    # 원점(후보지)을 선분에 투영
    t = -(
        x1 * dx
        + y1 * dy
    ) / denom

    t = max(
        0.0,
        min(1.0, t),
    )

    closest_x = (
        x1
        + t * dx
    )

    closest_y = (
        y1
        + t * dy
    )

    return math.sqrt(
        closest_x * closest_x
        + closest_y * closest_y
    )


def nearest_named_road(
    lon: float,
    lat: float,
) -> tuple[str, float]:
    """
    OSM 주요 도로망에서 가장 가까운
    이름 있는 도로를 찾는다.
    """
    best_name = ""
    best_distance = float("inf")

    for feature in road_features:
        properties = (
            feature.get(
                "properties",
                {}
            )
        )

        name = str(
            properties.get(
                "name",
                ""
            )
            or ""
        ).strip()

        if not name:
            continue

        geometry = feature.get(
            "geometry",
            {}
        )

        if (
            geometry.get("type")
            != "LineString"
        ):
            continue

        coords = geometry.get(
            "coordinates",
            []
        )

        if len(coords) < 2:
            continue

        for p1, p2 in zip(
            coords[:-1],
            coords[1:],
        ):
            distance = (
                point_segment_distance_m(
                    lon,
                    lat,
                    float(p1[0]),
                    float(p1[1]),
                    float(p2[0]),
                    float(p2[1]),
                )
            )

            if (
                distance
                < best_distance
            ):
                best_distance = distance
                best_name = name

    if not best_name:
        return "도로명 확인 필요", np.nan

    return (
        best_name,
        round(
            best_distance,
            1,
        ),
    )


# ============================================================
# 3. 새 취약도 Top 10 불러오기
# ============================================================

top = pd.read_csv(
    ANALYSIS
    / "08_top10_hotspots_with_security_lights.csv",
    encoding="utf-8-sig",
).copy()


# 새 분석 결과인지 확인
required_columns = [
    "grid_x",
    "grid_y",
    "중심경도",
    "중심위도",
    "야간유동인구",
    "버스정류장수",
    "CCTV수",
    "조명시설수",
    "안전수요점수",
    "시설공백점수",
    "격자취약도점수_보완",
    "격자취약도순위_보완",
]

missing = [
    col
    for col in required_columns
    if col not in top.columns
]

if missing:
    raise KeyError(
        "새 취약도 결과에 필요한 열이 없습니다: "
        + ", ".join(missing)
    )


# 혹시 이전 결과가 섞이지 않도록
# 순위 기준으로 다시 정렬하고 Top 10만 사용
top = (
    top.sort_values(
        "격자취약도순위_보완"
    )
    .head(10)
    .copy()
)


# ============================================================
# 4. 경찰기관 / 비상벨 불러오기
#
# 중요:
# 이 두 데이터는 취약도 점수에는 사용하지 않는다.
# 최종 후보지의 대응 접근성을 검토하는 보조지표다.
# ============================================================

police = load_clean(
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


bells = load_clean(
    "13_emergency_bells_point_clean.csv"
)

bells = standardize_wgs84(
    bells,
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


# ============================================================
# 5. 후보지역명 및 대응 접근성 계산
# ============================================================

candidate_names = []
road_distances = []

nearest_bell = []
bells_500m = []

nearest_police = []
police_1000m = []


for _, row in top.iterrows():
    lon = float(
        row["중심경도"]
    )

    lat = float(
        row["중심위도"]
    )

    # --------------------------------------------------------
    # 가장 가까운 OSM 도로명
    # --------------------------------------------------------
    road_name, road_distance = (
        nearest_named_road(
            lon,
            lat,
        )
    )

    candidate_names.append(
        f"{road_name} 인근"
    )

    road_distances.append(
        road_distance
    )


    # --------------------------------------------------------
    # 비상벨 접근성
    # --------------------------------------------------------
    bell_distance_array = (
        distances_m(
            lon,
            lat,
            bells,
        )
    )

    nearest_bell.append(
        round(
            safe_min_distance(
                bell_distance_array
            ),
            1,
        )
    )

    bells_500m.append(
        int(
            (
                bell_distance_array
                <= 500
            ).sum()
        )
    )


    # --------------------------------------------------------
    # 경찰기관 접근성
    # --------------------------------------------------------
    police_distance_array = (
        distances_m(
            lon,
            lat,
            police,
        )
    )

    nearest_police.append(
        round(
            safe_min_distance(
                police_distance_array
            ),
            1,
        )
    )

    police_1000m.append(
        int(
            (
                police_distance_array
                <= 1000
            ).sum()
        )
    )


top["후보지역"] = (
    candidate_names
)

top["인근도로거리_m"] = (
    road_distances
)

top["최근접_비상벨거리_m"] = (
    nearest_bell
)

top["반경500m_비상벨수"] = (
    bells_500m
)

top["최근접_경찰기관거리_m"] = (
    nearest_police
)

top["반경1000m_경찰기관수"] = (
    police_1000m
)


# ============================================================
# 6. 정책유형 분류
#
# 교통사고는 사용하지 않는다.
#
# 최종 순위는 위에서 계산된 취약도 순위를 그대로 유지하고,
# 여기서는 각 후보에 어떤 정책이 필요한지만 분류한다.
# ============================================================

def classify(row):
    cctv = int(
        row["CCTV수"]
    )

    lighting = int(
        row["조명시설수"]
    )

    # CCTV와 조명이 모두 없는 경우
    if (
        cctv == 0
        and lighting == 0
    ):
        return (
            "시설공백 최우선",
            "CCTV·조명시설 신규 배치 타당성 검토",
            "A",
        )

    # 조명은 있지만 CCTV가 없는 경우
    if (
        cctv == 0
        and lighting > 0
    ):
        return (
            "CCTV 보완",
            "기존 조명 활용 + CCTV 사각지대 보완 검토",
            "B",
        )

    # CCTV는 있지만 조명이 없는 경우
    if (
        cctv > 0
        and lighting == 0
    ):
        return (
            "조명 보완",
            "기존 CCTV 활용 + 보행 조도·조명 보완 검토",
            "B",
        )

    # 두 시설 모두 존재하는 경우
    return (
        "야간안심보행 관리",
        "야간 활동수요와 정류장 동선을 중심으로 시설 운영·보행환경 관리",
        "C",
    )


classified = top.apply(
    classify,
    axis=1,
    result_type="expand",
)

top["정책유형"] = (
    classified[0]
)

top["권장정책"] = (
    classified[1]
)

top["정책우선등급"] = (
    classified[2]
)


# ============================================================
# 7. 선정근거 생성
#
# 취약도에 실제로 사용된 변수만 선정근거에 사용한다.
# 경찰기관/비상벨은 별도의 대응접근성검토 열로 구분한다.
# ============================================================

def evidence(row):
    parts = []

    parts.append(
        "야간유동인구 "
        f"{float(row['야간유동인구']):,.1f}"
    )

    parts.append(
        "버스정류장 "
        f"{int(row['버스정류장수'])}개"
    )

    if int(
        row["CCTV수"]
    ) == 0:
        parts.append(
            "격자 내 CCTV 0"
        )
    else:
        parts.append(
            "CCTV "
            f"{int(row['CCTV수'])}개"
        )

    if int(
        row["조명시설수"]
    ) == 0:
        parts.append(
            "격자 내 조명시설 0"
        )
    else:
        parts.append(
            "조명시설 "
            f"{int(row['조명시설수'])}개"
        )

    parts.append(
        "안전수요점수 "
        f"{float(row['안전수요점수']):.3f}"
    )

    parts.append(
        "시설공백점수 "
        f"{float(row['시설공백점수']):.3f}"
    )

    return ", ".join(parts)


def response_evidence(row):
    bell_distance = float(
        row["최근접_비상벨거리_m"]
    )

    police_distance = float(
        row["최근접_경찰기관거리_m"]
    )

    return (
        f"비상벨 최근접 {bell_distance:,.0f}m"
        f" / 500m 내 {int(row['반경500m_비상벨수'])}개"
        f" / 경찰기관 최근접 {police_distance:,.0f}m"
        f" / 1km 내 {int(row['반경1000m_경찰기관수'])}곳"
    )


top["선정근거"] = top.apply(
    evidence,
    axis=1,
)

top["대응접근성검토"] = top.apply(
    response_evidence,
    axis=1,
)


# ============================================================
# 8. 최종 결과 정리
# ============================================================

result = top[
    [
        "격자취약도순위_보완",
        "정책우선등급",
        "후보지역",
        "인근도로거리_m",
        "중심경도",
        "중심위도",

        "야간유동인구",
        "버스정류장수",

        "CCTV수",
        "가로등수",
        "보안등수",
        "조명시설수",

        "안전수요점수",
        "시설공백점수",

        "격자취약도점수_보완",

        "최근접_비상벨거리_m",
        "반경500m_비상벨수",

        "최근접_경찰기관거리_m",
        "반경1000m_경찰기관수",

        "정책유형",
        "권장정책",
        "선정근거",
        "대응접근성검토",
    ]
].copy()


result = result.rename(
    columns={
        "격자취약도순위_보완":
            "최종순위",

        "격자취약도점수_보완":
            "최종취약도점수",
    }
)


result[
    "최종취약도점수"
] = (
    result[
        "최종취약도점수"
    ]
    .round(2)
)


result[
    "야간유동인구"
] = (
    result[
        "야간유동인구"
    ]
    .round(2)
)


result[
    "안전수요점수"
] = (
    result[
        "안전수요점수"
    ]
    .round(4)
)


result[
    "시설공백점수"
] = (
    result[
        "시설공백점수"
    ]
    .round(4)
)


result.to_csv(
    ANALYSIS
    / "10_final_policy_priority.csv",
    index=False,
    encoding="utf-8-sig",
)


# ============================================================
# 9. 요약 보고서 자동 생성
# ============================================================

top3 = result.head(3)


top3_lines = []

for _, row in top3.iterrows():
    top3_lines.append(
        f"- {int(row['최종순위'])}위 "
        f"{row['후보지역']}: "
        f"취약도 {row['최종취약도점수']:.2f}, "
        f"야간유동인구 {row['야간유동인구']:,.1f}, "
        f"CCTV {int(row['CCTV수'])}개, "
        f"조명시설 {int(row['조명시설수'])}개"
    )


type_lines = []

for policy_type, frame in result.groupby(
    "정책유형",
    sort=False,
):
    names = ", ".join(
        frame["후보지역"]
        .astype(str)
        .tolist()
    )

    type_lines.append(
        f"- {policy_type}: {names}"
    )


summary = f"""# 유성구 야간 보행안전 취약지역 최종 후보안

## 취약도 산정식

- 안전수요 = 0.60 × 야간 유동인구 + 0.40 × 버스정류장
- 시설공백 = 0.55 × CCTV 부족 + 0.45 × 조명시설 부족
- 최종 취약도 = 100 × (0.65 × 안전수요 + 0.35 × 시설공백)
- 조명시설 = 가로등 + 보안등

※ 각 입력지표는 log(1+x) 변환 후 Min-Max 정규화하였다.

## 핵심 원칙

- 교통사고 데이터는 최종 취약도 산정에 사용하지 않았다.
- 경찰기관과 비상벨은 취약도 점수 및 순위에는 사용하지 않았다.
- 경찰기관과 비상벨은 최종 후보지의 대응 접근성을 검토하기 위한 보조지표로만 활용하였다.
- 최종 순위는 취약도 점수 순위를 그대로 유지하고, 정책유형은 시설 구성에 따라 분류하였다.

## 상위 3개 후보

{chr(10).join(top3_lines)}

## 정책유형별 후보

{chr(10).join(type_lines)}

## 해석

취약도 상위지역은 야간 활동수요가 높은 동시에 CCTV 또는 조명시설의 상대적 공백이 큰 500m 격자이다.
따라서 본 결과는 범죄발생 가능성을 예측한 결과가 아니라, 야간 보행안전 시설과 관리정책의 상대적 우선 검토지역을 제시한 결과로 해석한다.

## 대응 접근성 보조검토

비상벨 최근접 거리와 반경 500m 비상벨 수, 경찰기관 최근접 거리와 반경 1km 경찰기관 수를 산출하였다.
이 값들은 취약도 산정식에 포함하지 않고 후보지역별 대응시설 접근성을 설명하는 보조자료로 사용한다.

## 분석 한계

- 가중치 0.60/0.40, 0.55/0.45, 0.65/0.35는 분석 설계상 적용한 가중치이며 인과적 효과를 의미하지 않는다.
- 야간 유동인구는 2025-08~2026-07, 22:00~06:00 자료 중 12개월이 모두 확보된 격자를 사용하였다.
- 유동인구 원자료는 50m 격자를 500m 단위로 집계한 자료이며 개인정보 보호 기준이 적용되어 있다.
- 비상벨과 경찰기관은 시설의 존재 및 공간적 접근성을 확인하는 용도로 사용하며 실제 출동시간이나 시설 정상 작동 여부를 의미하지 않는다.
- 현재 경계 및 도로망은 저장소의 작업용 공간자료를 사용하였다.

## 사용 데이터

- CCTV
- 가로등 및 보안등
- 유성구청 제공 야간 유동인구
- 마을버스 정류장
- 경찰기관
- 비상벨
"""


(
    ANALYSIS
    / "11_final_policy_summary.md"
).write_text(
    summary,
    encoding="utf-8",
)


# ============================================================
# 10. 실행 결과 출력
# ============================================================

print()
print("=" * 90)
print(
    "유성구 야간 보행안전 정책 후보 정리 완료"
)
print("=" * 90)

print(
    f"최종 후보: {len(result)}곳"
)

print(
    f"비상벨 데이터: {len(bells)}건"
)

print(
    f"경찰기관 데이터: {len(police)}곳"
)

print()
print(
    "※ 경찰기관·비상벨은 취약도 점수에 포함하지 않고 "
    "보조 검증에만 사용했습니다."
)

print()
print(
    result[
        [
            "최종순위",
            "후보지역",
            "최종취약도점수",
            "야간유동인구",
            "버스정류장수",
            "CCTV수",
            "조명시설수",
            "최근접_비상벨거리_m",
            "최근접_경찰기관거리_m",
            "정책유형",
        ]
    ].to_string(
        index=False
    )
)