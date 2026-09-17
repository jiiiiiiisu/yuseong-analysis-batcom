import json
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
GEO = ROOT / "geo"
ANALYSIS = ROOT / "analysis"
MAPS = ROOT / "maps"

data = pd.read_csv(ANALYSIS / "10_final_policy_priority.csv", encoding="utf-8-sig")
with open(GEO / "yuseong_boundary.geojson", encoding="utf-8") as stream:
    geom = json.load(stream)["features"][0]["geometry"]
polygons = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
with open(GEO / "yuseong_major_roads.geojson", encoding="utf-8") as stream:
    roads = json.load(stream)["features"]

points = [p for polygon in polygons for ring in polygon for p in ring]
lons = [p[0] for p in points]
lats = [p[1] for p in points]
W, H = 1600, 1300
map_left, map_top, map_right, map_bottom = 80, 185, 1160, 1190


def project(lon, lat):
    x = map_left + (lon - min(lons)) / (max(lons) - min(lons)) * (map_right - map_left)
    y = map_bottom - (lat - min(lats)) / (max(lats) - min(lats)) * (map_bottom - map_top)
    return x, y


font = r"C:\Windows\Fonts\malgun.ttf"
bold = r"C:\Windows\Fonts\malgunbd.ttf"
img = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(img, "RGBA")
draw.text((70, 45), "유성구 야간안전 정책 우선지역", font=ImageFont.truetype(bold, 46), fill="#111827")
draw.text((72, 108), "보안등 결합 500m 격자 · 정책유형별 최종 후보 10곳", font=ImageFont.truetype(font, 24), fill="#64748b")

for polygon in polygons:
    draw.polygon([project(*p[:2]) for p in polygon[0]], fill="#f3f6f9", outline="#475569", width=4)
for feature in roads:
    coords = feature["geometry"]["coordinates"]
    kind = feature["properties"].get("highway")
    color, width = ("#94a3b8", 3) if kind in {"motorway", "trunk"} else ("#cbd5e1", 2)
    draw.line([project(*p[:2]) for p in coords], fill=color, width=width)

colors = {"시설공백 최우선": "#dc2626", "CCTV 보완": "#2563eb", "교통·보행안전": "#f59e0b", "복합 관리": "#059669"}
for _, row in data.iterrows():
    x, y = project(row["중심경도"], row["중심위도"])
    color = colors[row["정책유형"]]
    draw.ellipse((x-25, y-25, x+25, y+25), fill=color+"CC", outline="#ffffff", width=3)
    draw.text((x, y), str(int(row["최종순위"])), font=ImageFont.truetype(bold, 22), fill="white", anchor="mm")

draw.rounded_rectangle((1200, 190, 1550, 740), radius=18, fill="#f8fafc", outline="#d8e0ea", width=2)
draw.text((1230, 220), "최종 우선순위", font=ImageFont.truetype(bold, 25), fill="#142A63")
small = ImageFont.truetype(font, 17)
small_bold = ImageFont.truetype(bold, 17)
for i, row in data.iterrows():
    y = 270 + i*43
    color = colors[row["정책유형"]]
    draw.ellipse((1228, y-8, 1244, y+8), fill=color)
    draw.text((1255, y), f"{int(row['최종순위'])}. {row['후보지역']}", font=small_bold, fill="#1f2937", anchor="lm")

legend_y = 815
draw.text((1225, legend_y), "정책유형", font=ImageFont.truetype(bold, 22), fill="#142A63")
for i, (label, color) in enumerate(colors.items()):
    y = legend_y + 42 + i*40
    draw.ellipse((1228, y-8, 1244, y+8), fill=color)
    draw.text((1255, y), label, font=small, fill="#334155", anchor="lm")

draw.text((1545, 1218), "경계·도로: OpenStreetMap(작업용)", font=ImageFont.truetype(font, 16), fill="#64748b", anchor="rm")
MAPS.mkdir(exist_ok=True)
img.save(MAPS / "02_final_policy_priority_map.png")
print(MAPS / "02_final_policy_priority_map.png")
