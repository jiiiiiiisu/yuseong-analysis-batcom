from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
GEO = ROOT / "geo"
ANALYSIS = ROOT / "analysis"
MAPS = ROOT / "maps"

MAPS.mkdir(exist_ok=True)


# ============================================================
# 1. 최종 정책 후보 불러오기
# ============================================================

data = pd.read_csv(
    ANALYSIS / "10_final_policy_priority.csv",
    encoding="utf-8-sig",
)

data = data.sort_values(
    "최종순위"
).copy()


required_columns = [
    "최종순위",
    "후보지역",
    "중심경도",
    "중심위도",
    "최종취약도점수",
    "야간유동인구",
    "버스정류장수",
    "CCTV수",
    "조명시설수",
    "정책유형",
]

missing = [
    col
    for col in required_columns
    if col not in data.columns
]

if missing:
    raise KeyError(
        "최종 정책 후보 파일에 필요한 열이 없습니다: "
        + ", ".join(missing)
    )


# ============================================================
# 2. 유성구 경계 및 도로망 불러오기
# ============================================================

with open(
    GEO / "yuseong_boundary.geojson",
    encoding="utf-8",
) as stream:
    geom = json.load(stream)["features"][0]["geometry"]


polygons = (
    [geom["coordinates"]]
    if geom["type"] == "Polygon"
    else geom["coordinates"]
)


with open(
    GEO / "yuseong_major_roads.geojson",
    encoding="utf-8",
) as stream:
    roads = json.load(stream)["features"]


points = [
    p
    for polygon in polygons
    for ring in polygon
    for p in ring
]

lons = [
    p[0]
    for p in points
]

lats = [
    p[1]
    for p in points
]


# ============================================================
# 3. 지도 영역 설정
# ============================================================

W = 1700
H = 1350

map_left = 70
map_top = 190
map_right = 1160
map_bottom = 1220


def project(
    lon: float,
    lat: float,
):
    x = (
        map_left
        + (lon - min(lons))
        / (max(lons) - min(lons))
        * (map_right - map_left)
    )

    y = (
        map_bottom
        - (lat - min(lats))
        / (max(lats) - min(lats))
        * (map_bottom - map_top)
    )

    return x, y


# ============================================================
# 4. 폰트
# ============================================================

font_path = (
    r"C:\Windows\Fonts\malgun.ttf"
)

bold_path = (
    r"C:\Windows\Fonts\malgunbd.ttf"
)


f_title = ImageFont.truetype(
    bold_path,
    44,
)

f_sub = ImageFont.truetype(
    font_path,
    22,
)

f_rank = ImageFont.truetype(
    bold_path,
    21,
)

f_panel_title = ImageFont.truetype(
    bold_path,
    24,
)

f_panel = ImageFont.truetype(
    font_path,
    16,
)

f_panel_bold = ImageFont.truetype(
    bold_path,
    16,
)

f_note = ImageFont.truetype(
    font_path,
    15,
)


# ============================================================
# 5. 기본 캔버스
# ============================================================

img = Image.new(
    "RGB",
    (W, H),
    "white",
)

draw = ImageDraw.Draw(
    img,
    "RGBA",
)


draw.text(
    (70, 45),
    "유성구 야간 보행안전 정책 우선지역",
    font=f_title,
    fill="#111827",
)

draw.text(
    (72, 108),
    (
        "500m 격자 · 야간 유동인구·버스수요·"
        "안전시설 공백 기반 최종 후보 10곳"
    ),
    font=f_sub,
    fill="#64748b",
)

draw.text(
    (72, 145),
    (
        "※ 경찰기관·비상벨은 취약도 점수에 포함하지 않고 "
        "후보지역 대응 접근성 검토에만 활용"
    ),
    font=f_note,
    fill="#64748b",
)


# ============================================================
# 6. 유성구 경계
# ============================================================

for polygon in polygons:
    outer = [
        project(
            *p[:2]
        )
        for p in polygon[0]
    ]

    draw.polygon(
        outer,
        fill="#f3f6f9",
        outline="#475569",
        width=4,
    )


# ============================================================
# 7. 주요 도로
# ============================================================

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
        road_color = "#94a3b8"
        road_width = 3

    elif kind == "primary":
        road_color = "#cbd5e1"
        road_width = 2

    else:
        road_color = "#e2e8f0"
        road_width = 1

    road_points = [
        project(
            *p[:2]
        )
        for p in coords
    ]

    if len(
        road_points
    ) >= 2:
        draw.line(
            road_points,
            fill=road_color,
            width=road_width,
        )


# ============================================================
# 8. 정책유형별 표시 설정
# ============================================================

colors = {
    "시설공백 최우선": "#dc2626",
    "CCTV 보완": "#2563eb",
    "조명 보완": "#f59e0b",
    "야간안심보행 관리": "#059669",
}


unknown_types = set(
    data["정책유형"].dropna()
) - set(colors)

if unknown_types:
    raise ValueError(
        "정의되지 않은 정책유형이 있습니다: "
        + ", ".join(
            sorted(
                unknown_types
            )
        )
    )


# ============================================================
# 9. 최종 후보 10곳 지도 표시
# ============================================================

for _, row in data.iterrows():

    x, y = project(
        float(
            row["중심경도"]
        ),
        float(
            row["중심위도"]
        ),
    )

    policy_type = (
        row["정책유형"]
    )

    color = (
        colors[
            policy_type
        ]
    )

    draw.ellipse(
        (
            x - 27,
            y - 27,
            x + 27,
            y + 27,
        ),
        fill=color + "DD",
        outline="#ffffff",
        width=4,
    )

    draw.text(
        (
            x,
            y,
        ),
        str(
            int(
                row["최종순위"]
            )
        ),
        font=f_rank,
        fill="white",
        anchor="mm",
    )


# ============================================================
# 10. 우측 순위 패널
# ============================================================

panel_left = 1190
panel_top = 190
panel_right = 1660
panel_bottom = 845


draw.rounded_rectangle(
    (
        panel_left,
        panel_top,
        panel_right,
        panel_bottom,
    ),
    radius=18,
    fill="#f8fafc",
    outline="#d8e0ea",
    width=2,
)


draw.text(
    (
        panel_left + 28,
        panel_top + 28,
    ),
    "최종 우선순위",
    font=f_panel_title,
    fill="#142A63",
)


start_y = (
    panel_top
    + 85
)

row_height = 52


for i, (_, row) in enumerate(
    data.iterrows()
):

    y = (
        start_y
        + i
        * row_height
    )

    color = (
        colors[
            row["정책유형"]
        ]
    )

    draw.ellipse(
        (
            panel_left + 30,
            y - 8,
            panel_left + 46,
            y + 8,
        ),
        fill=color,
    )

    candidate_name = str(
        row["후보지역"]
    )

    if len(
        candidate_name
    ) > 19:
        candidate_name = (
            candidate_name[:18]
            + "…"
        )

    rank_text = (
        f"{int(row['최종순위'])}. "
        f"{candidate_name}"
    )

    draw.text(
        (
            panel_left + 58,
            y,
        ),
        rank_text,
        font=f_panel_bold,
        fill="#1f2937",
        anchor="lm",
    )

    score_text = (
        f"취약도 "
        f"{float(row['최종취약도점수']):.2f}"
    )

    draw.text(
        (
            panel_right - 22,
            y,
        ),
        score_text,
        font=f_panel,
        fill="#64748b",
        anchor="rm",
    )


# ============================================================
# 11. 정책유형 범례
# ============================================================

legend_top = 890


draw.rounded_rectangle(
    (
        panel_left,
        legend_top,
        panel_right,
        1130,
    ),
    radius=18,
    fill="#f8fafc",
    outline="#d8e0ea",
    width=2,
)


draw.text(
    (
        panel_left + 28,
        legend_top + 25,
    ),
    "정책유형",
    font=f_panel_title,
    fill="#142A63",
)


for i, (
    label,
    color,
) in enumerate(
    colors.items()
):

    y = (
        legend_top
        + 80
        + i * 43
    )

    draw.ellipse(
        (
            panel_left + 30,
            y - 8,
            panel_left + 46,
            y + 8,
        ),
        fill=color,
    )

    draw.text(
        (
            panel_left + 60,
            y,
        ),
        label,
        font=f_panel,
        fill="#334155",
        anchor="lm",
    )


# ============================================================
# 12. 하단 설명
# ============================================================

draw.text(
    (
        70,
        1280,
    ),
    (
        "취약도 = 100 × "
        "[0.65 × (0.60 × 야간유동인구 + 0.40 × 버스정류장) "
        "+ 0.35 × (0.55 × CCTV부족 + 0.45 × 조명시설부족)]"
    ),
    font=f_note,
    fill="#475569",
)


draw.text(
    (
        W - 55,
        1310,
    ),
    "경계·도로: OpenStreetMap(작업용)",
    font=f_note,
    fill="#64748b",
    anchor="rm",
)


# ============================================================
# 13. 저장
# ============================================================

output_path = (
    MAPS
    / "02_final_policy_priority_map.png"
)

img.save(
    output_path
)


print()
print("=" * 75)
print(
    "유성구 야간 보행안전 최종 정책지도 생성 완료"
)
print("=" * 75)

print(
    output_path
)

print()

print(
    data[
        [
            "최종순위",
            "후보지역",
            "최종취약도점수",
            "정책유형",
        ]
    ].to_string(
        index=False
    )
)