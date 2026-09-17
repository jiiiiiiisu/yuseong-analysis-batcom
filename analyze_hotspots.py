from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "data_clean"
GEO = ROOT / "geo"
ANALYSIS = ROOT / "analysis"
MAPS = ROOT / "maps"
ANALYSIS.mkdir(exist_ok=True)
MAPS.mkdir(exist_ok=True)


def load_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(CLEAN / name, encoding="utf-8-sig", low_memory=False)


with open(GEO / "yuseong_boundary.geojson", encoding="utf-8") as f:
    boundary_fc = json.load(f)
geometry = boundary_fc["features"][0]["geometry"]


def polygon_rings(geom):
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return geom["coordinates"]
    raise ValueError(f"Unsupported geometry: {geom['type']}")


POLYGONS = polygon_rings(geometry)


def in_ring(lon: float, lat: float, ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][:2]
        xj, yj = ring[j][:2]
        if ((yi > lat) != (yj > lat)) and (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi):
            inside = not inside
        j = i
    return inside


def in_boundary(lon: float, lat: float) -> bool:
    if not np.isfinite(lon) or not np.isfinite(lat):
        return False
    for polygon in POLYGONS:
        if not polygon:
            continue
        if in_ring(lon, lat, polygon[0]) and not any(in_ring(lon, lat, hole) for hole in polygon[1:]):
            return True
    return False


def clip_points(df: pd.DataFrame) -> pd.DataFrame:
    lon = pd.to_numeric(df["경도_WGS84"], errors="coerce")
    lat = pd.to_numeric(df["위도_WGS84"], errors="coerce")
    mask = [in_boundary(x, y) for x, y in zip(lon, lat)]
    return df.loc[mask].copy()


cctv = clip_points(load_csv("01_cctv_clean.csv"))
lights = clip_points(load_csv("02_streetlights_yuseong.csv"))
bus = clip_points(load_csv("03_bus_stops_daejeon.csv"))
accidents = clip_points(load_csv("05c_traffic_accidents_night_spatial_valid.csv"))
police = clip_points(load_csv("08_police_stations_clean.csv"))
bus.to_csv(CLEAN / "03b_bus_stops_yuseong.csv", index=False, encoding="utf-8-sig")


# Local metric coordinates for a 500 m grid.
all_boundary_points = [pt for polygon in POLYGONS for ring in polygon for pt in ring]
lons = np.array([p[0] for p in all_boundary_points], dtype=float)
lats = np.array([p[1] for p in all_boundary_points], dtype=float)
lon0, lat0 = float(lons.min()), float(lats.min())
mx = 111_320 * math.cos(math.radians(float(lats.mean())))
my = 111_320
cell_size = 500.0


def add_cell(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["grid_x"] = np.floor((pd.to_numeric(result["경도_WGS84"], errors="coerce") - lon0) * mx / cell_size).astype("Int64")
    result["grid_y"] = np.floor((pd.to_numeric(result["위도_WGS84"], errors="coerce") - lat0) * my / cell_size).astype("Int64")
    return result


cctv_g, lights_g, bus_g, acc_g = map(add_cell, [cctv, lights, bus, accidents])
max_x = math.ceil((lons.max() - lon0) * mx / cell_size)
max_y = math.ceil((lats.max() - lat0) * my / cell_size)
cells = []
for gx in range(max_x + 1):
    for gy in range(max_y + 1):
        center_lon = lon0 + (gx + 0.5) * cell_size / mx
        center_lat = lat0 + (gy + 0.5) * cell_size / my
        if in_boundary(center_lon, center_lat):
            sample_inside = 0
            sample_total = 25
            for sx in range(5):
                for sy in range(5):
                    sample_lon = lon0 + (gx + (sx + 0.5) / 5) * cell_size / mx
                    sample_lat = lat0 + (gy + (sy + 0.5) / 5) * cell_size / my
                    sample_inside += int(in_boundary(sample_lon, sample_lat))
            cells.append((gx, gy, center_lon, center_lat, sample_inside / sample_total))
grid = pd.DataFrame(cells, columns=["grid_x", "grid_y", "중심경도", "중심위도", "경계포함비율"])


def counts(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    return frame.groupby(["grid_x", "grid_y"], as_index=False).size().rename(columns={"size": name})


for frame, name in [(cctv_g, "CCTV수"), (lights_g, "가로등수"), (bus_g, "버스정류장수"), (acc_g, "야간사고수")]:
    grid = grid.merge(counts(frame, name), on=["grid_x", "grid_y"], how="left")
    grid[name] = grid[name].fillna(0).astype(int)


def minmax(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    if x.max() == x.min():
        return pd.Series(0.5, index=x.index)
    return (x - x.min()) / (x.max() - x.min())


grid["버스수요_정규화"] = minmax(np.log1p(grid["버스정류장수"]))
grid["야간사고_정규화"] = minmax(np.log1p(grid["야간사고수"]))
grid["CCTV부족_정규화"] = 1 - minmax(np.log1p(grid["CCTV수"]))
grid["가로등부족_정규화"] = 1 - minmax(np.log1p(grid["가로등수"]))
grid["안전수요점수"] = 0.40 * grid["버스수요_정규화"] + 0.60 * grid["야간사고_정규화"]
grid["시설공백점수"] = 0.55 * grid["CCTV부족_정규화"] + 0.45 * grid["가로등부족_정규화"]
grid["격자취약도점수"] = (0.65 * grid["안전수요점수"] + 0.35 * grid["시설공백점수"]) * 100
grid["분석대상여부"] = (((grid["버스정류장수"] > 0) | (grid["야간사고수"] > 0)) & (grid["경계포함비율"] >= 0.5))
eligible = grid[grid["분석대상여부"]].copy()
eligible["격자취약도순위"] = eligible["격자취약도점수"].rank(method="min", ascending=False).astype(int)
eligible = eligible.sort_values(["격자취약도순위", "grid_y", "grid_x"])
eligible.to_csv(ANALYSIS / "03_grid_500m_hotspot_scores.csv", index=False, encoding="utf-8-sig")
eligible.head(30).to_csv(ANALYSIS / "04_top30_hotspots.csv", index=False, encoding="utf-8-sig")


# Static map using sourced boundary and major-road geometry.
with open(GEO / "yuseong_major_roads.geojson", encoding="utf-8") as f:
    roads = json.load(f)["features"]

W, H = 1500, 1500
margin = 100
map_left, map_top, map_right, map_bottom = 90, 190, 1410, 1370
lon_min, lon_max = lons.min(), lons.max()
lat_min, lat_max = lats.min(), lats.max()


def project(lon, lat):
    x = map_left + (lon - lon_min) / (lon_max - lon_min) * (map_right - map_left)
    y = map_bottom - (lat - lat_min) / (lat_max - lat_min) * (map_bottom - map_top)
    return x, y


img = Image.new("RGB", (W, H), "white")
draw = ImageDraw.Draw(img, "RGBA")
font_path = r"C:\Windows\Fonts\malgun.ttf"
bold_path = r"C:\Windows\Fonts\malgunbd.ttf"
f_title = ImageFont.truetype(bold_path, 46)
f_sub = ImageFont.truetype(font_path, 24)
f_label = ImageFont.truetype(bold_path, 23)
f_small = ImageFont.truetype(font_path, 19)
draw.text((80, 55), "유성구 야간안전 취약지점 후보", font=f_title, fill="#222222")
draw.text((82, 120), "500m 격자 · 상위 20개 후보 · 도로망과 안전시설을 결합한 1차 분석", font=f_sub, fill="#666666")

# Boundary fill and road network.
for polygon in POLYGONS:
    outer = [project(*p[:2]) for p in polygon[0]]
    draw.polygon(outer, fill="#f3f6f9", outline="#4b5563", width=4)
for feature in roads:
    coords = feature["geometry"]["coordinates"]
    kind = feature["properties"].get("highway")
    if kind in {"motorway", "trunk"}:
        color, width = "#9ca3af", 3
    elif kind == "primary":
        color, width = "#cbd5e1", 2
    else:
        color, width = "#e2e8f0", 1
    pts = [project(*p[:2]) for p in coords]
    if len(pts) >= 2:
        draw.line(pts, fill=color, width=width)

# Context points: police and CCTV.
for _, row in cctv.iterrows():
    x, y = project(float(row["경도_WGS84"]), float(row["위도_WGS84"]))
    draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill="#2563eb")
for _, row in police.iterrows():
    x, y = project(float(row["경도_WGS84"]), float(row["위도_WGS84"]))
    draw.regular_polygon((x, y, 8), 4, rotation=45, fill="#111827")

# Hotspot circles.
top20 = eligible.head(20)
score_min, score_max = top20["격자취약도점수"].min(), top20["격자취약도점수"].max()
for idx, (_, row) in enumerate(top20.iterrows(), start=1):
    x, y = project(float(row["중심경도"]), float(row["중심위도"]))
    norm = (row["격자취약도점수"] - score_min) / ((score_max - score_min) or 1)
    radius = 13 + 17 * norm
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(220, 38, 38, 120), outline="#991b1b", width=2)
    if idx <= 10:
        draw.text((x, y), str(idx), font=f_label, fill="white", anchor="mm", stroke_width=2, stroke_fill="#991b1b")

# Legend.
legend_y = 1415
draw.ellipse((90, legend_y - 8, 106, legend_y + 8), fill=(220, 38, 38, 150), outline="#991b1b")
draw.text((118, legend_y), "취약지점 후보", font=f_small, fill="#333333", anchor="lm")
draw.ellipse((330, legend_y - 3, 336, legend_y + 3), fill="#2563eb")
draw.text((348, legend_y), "CCTV", font=f_small, fill="#333333", anchor="lm")
draw.regular_polygon((475, legend_y, 7), 4, rotation=45, fill="#111827")
draw.text((490, legend_y), "경찰기관", font=f_small, fill="#333333", anchor="lm")
draw.text((W - 85, legend_y), "경계·도로: OpenStreetMap", font=f_small, fill="#666666", anchor="rm")
img.save(MAPS / "01_yuseong_500m_hotspots.png")

print(f"유성구 버스정류장: {len(bus):,}건")
print(f"격자: 전체 {len(grid):,}개, 분석대상 {len(eligible):,}개")
print(eligible.head(10)[["격자취약도순위", "중심경도", "중심위도", "격자취약도점수", "버스정류장수", "야간사고수", "CCTV수", "가로등수"]].to_string(index=False))
