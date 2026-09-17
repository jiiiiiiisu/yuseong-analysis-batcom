from __future__ import annotations

import json
import math
import os
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data_raw"
CLEAN = ROOT / "data_clean"
ANALYSIS = ROOT / "analysis"
GEO = ROOT / "geo"
ENDPOINT = "https://apis.data.go.kr/6300000/GetScltListService1/getScltList1"


def fetch_all() -> list[dict]:
    encoded_key = os.environ.get("SCLT_API_KEY")
    if not encoded_key:
        raise RuntimeError("SCLT_API_KEY is required")
    context = ssl._create_unverified_context()
    rows: list[dict] = []
    page = 1
    page_size = 10000
    total = None
    while total is None or len(rows) < total:
        query = (
            f"serviceKey={encoded_key}&pageNo={page}&numOfRows={page_size}&type=json"
        )
        with urllib.request.urlopen(f"{ENDPOINT}?{query}", context=context, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        header = payload["response"]["header"]
        if header.get("resultCode") != "00":
            raise RuntimeError(f"API error: {header}")
        body = payload["response"]["body"]
        total = int(body["totalCount"])
        items = body.get("items", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        rows.extend(items)
        if not items:
            break
        page += 1
    return rows[:total]


def in_ring(lon: float, lat: float, ring) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][:2]
        xj, yj = ring[j][:2]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi
        ):
            inside = not inside
        j = i
    return inside


def load_polygons():
    with open(GEO / "yuseong_boundary.geojson", encoding="utf-8") as stream:
        geom = json.load(stream)["features"][0]["geometry"]
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    return geom["coordinates"]


def in_boundary(lon: float, lat: float, polygons) -> bool:
    if not np.isfinite(lon) or not np.isfinite(lat):
        return False
    for polygon in polygons:
        if in_ring(lon, lat, polygon[0]) and not any(
            in_ring(lon, lat, hole) for hole in polygon[1:]
        ):
            return True
    return False


def minmax(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    if x.max() == x.min():
        return pd.Series(0.5, index=x.index)
    return (x - x.min()) / (x.max() - x.min())


def distances_m(lon: float, lat: float, frame: pd.DataFrame) -> np.ndarray:
    point_lon = frame["경도_WGS84"].to_numpy(float)
    point_lat = frame["위도_WGS84"].to_numpy(float)
    x = (point_lon - lon) * 111_320 * math.cos(math.radians(lat))
    y = (point_lat - lat) * 111_320
    return np.sqrt(x * x + y * y)


def main():
    rows = fetch_all()
    with open(RAW / "09_security_lights_api.json", "w", encoding="utf-8") as stream:
        json.dump(rows, stream, ensure_ascii=False)

    all_lights = pd.DataFrame(
        {
            "보안등위치명": [r.get("LMP_LC_NM", "") for r in rows],
            "설치개수": [r.get("INSTALLATION_CO", 0) for r in rows],
            "도로명주소": [r.get("RDNMADR", "") for r in rows],
            "지번주소": [r.get("LNMADR", "") for r in rows],
            "위도_WGS84": [r.get("LATITUDE") for r in rows],
            "경도_WGS84": [r.get("LONGITUDE") for r in rows],
            "설치유형": [r.get("INSTALLATION_TYPE", "") for r in rows],
            "기준일자": [r.get("REFERENCEDATE", "") for r in rows],
        }
    )
    for column in ["설치개수", "위도_WGS84", "경도_WGS84"]:
        all_lights[column] = pd.to_numeric(all_lights[column], errors="coerce")
    all_lights = all_lights.dropna(subset=["위도_WGS84", "경도_WGS84"]).copy()
    all_lights["설치개수"] = all_lights["설치개수"].fillna(1).clip(lower=1).astype(int)

    polygons = load_polygons()
    address_mask = (
        all_lights["도로명주소"].fillna("").str.contains("유성구")
        | all_lights["지번주소"].fillna("").str.contains("유성구")
    )
    spatial_mask = [
        in_boundary(lon, lat, polygons)
        for lon, lat in zip(all_lights["경도_WGS84"], all_lights["위도_WGS84"])
    ]
    yuseong = all_lights.loc[address_mask | np.array(spatial_mask)].copy()
    yuseong.to_csv(CLEAN / "09_security_lights_yuseong.csv", index=False, encoding="utf-8-sig")

    grid = pd.read_csv(ANALYSIS / "03_grid_500m_hotspot_scores.csv", encoding="utf-8-sig")
    # Reconstruct the existing 500 m grid origin from its published cell centers.
    lat0_values = grid["중심위도"] - (grid["grid_y"] + 0.5) * 500 / 111_320
    lat0 = float(lat0_values.median())
    mean_lat = float(grid["중심위도"].mean())
    mx = 111_320 * math.cos(math.radians(mean_lat))
    lon0_values = grid["중심경도"] - (grid["grid_x"] + 0.5) * 500 / mx
    lon0 = float(lon0_values.median())

    yuseong["grid_x"] = np.floor((yuseong["경도_WGS84"] - lon0) * mx / 500).astype(int)
    yuseong["grid_y"] = np.floor((yuseong["위도_WGS84"] - lat0) * 111_320 / 500).astype(int)
    security_counts = (
        yuseong.groupby(["grid_x", "grid_y"], as_index=False)["설치개수"]
        .sum()
        .rename(columns={"설치개수": "보안등수"})
    )
    revised = grid.merge(security_counts, on=["grid_x", "grid_y"], how="left")
    revised["보안등수"] = revised["보안등수"].fillna(0).astype(int)
    revised["조명시설수"] = revised["가로등수"] + revised["보안등수"]
    revised["조명시설부족_정규화"] = 1 - minmax(np.log1p(revised["조명시설수"]))
    revised["시설공백점수_보완"] = (
        0.55 * revised["CCTV부족_정규화"]
        + 0.45 * revised["조명시설부족_정규화"]
    )
    revised["격자취약도점수_보완"] = (
        0.65 * revised["안전수요점수"] + 0.35 * revised["시설공백점수_보완"]
    ) * 100
    revised["격자취약도순위_보완"] = (
        revised["격자취약도점수_보완"].rank(method="min", ascending=False).astype(int)
    )
    revised = revised.sort_values(["격자취약도순위_보완", "grid_y", "grid_x"])
    revised.to_csv(
        ANALYSIS / "07_grid_500m_hotspot_scores_with_security_lights.csv",
        index=False,
        encoding="utf-8-sig",
    )
    revised.head(10).to_csv(
        ANALYSIS / "08_top10_hotspots_with_security_lights.csv",
        index=False,
        encoding="utf-8-sig",
    )

    candidates = pd.read_csv(
        ANALYSIS / "05_top10_hotspot_candidates_labeled.csv", encoding="utf-8-sig"
    )
    revised_lookup = revised.set_index(["grid_x", "grid_y"])
    verification_rows = []
    for _, site in candidates.iterrows():
        lon, lat = float(site["중심경도"]), float(site["중심위도"])
        distances = distances_m(lon, lat, yuseong)
        key = (int(site["grid_x"]), int(site["grid_y"]))
        rev = revised_lookup.loc[key]
        verification_rows.append(
            {
                "기존순위": int(site["격자취약도순위"]),
                "후보지역": site["인근지역_도로명"],
                "중심경도": lon,
                "중심위도": lat,
                "격자내_가로등수": int(site["가로등수"]),
                "격자내_보안등수": int(rev["보안등수"]),
                "격자내_조명시설수": int(rev["조명시설수"]),
                "최근접_보안등거리_m": round(float(np.nanmin(distances)), 1),
                "반경250m_보안등수": int(yuseong.loc[distances <= 250, "설치개수"].sum()),
                "반경500m_보안등수": int(yuseong.loc[distances <= 500, "설치개수"].sum()),
                "반경1000m_보안등수": int(yuseong.loc[distances <= 1000, "설치개수"].sum()),
                "보완후_취약도점수": round(float(rev["격자취약도점수_보완"]), 2),
                "보완후_순위": int(rev["격자취약도순위_보완"]),
            }
        )
    verification = pd.DataFrame(verification_rows).sort_values("보완후_순위")
    verification.to_csv(
        ANALYSIS / "09_candidate_verification_with_security_lights.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print(f"API total: {len(rows):,}")
    print(f"Yuseong security-light records: {len(yuseong):,}")
    print(f"Yuseong installation count: {yuseong['설치개수'].sum():,}")
    print(verification.to_string(index=False))


if __name__ == "__main__":
    main()
