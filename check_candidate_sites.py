import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
CLEAN = ROOT / "data_clean"
ANALYSIS = ROOT / "analysis"


def load(name):
    return pd.read_csv(CLEAN / name, encoding="utf-8-sig", low_memory=False)


def distances_m(lon, lat, frame):
    point_lon = pd.to_numeric(frame["경도_WGS84"], errors="coerce").to_numpy(float)
    point_lat = pd.to_numeric(frame["위도_WGS84"], errors="coerce").to_numpy(float)
    x = (point_lon - lon) * 111_320 * math.cos(math.radians(lat))
    y = (point_lat - lat) * 111_320
    return np.sqrt(x * x + y * y)


hotspots = pd.read_csv(ANALYSIS / "05_top10_hotspot_candidates_labeled.csv", encoding="utf-8-sig")
cctv = load("01_cctv_clean.csv")
lights = load("02_streetlights_yuseong.csv")
bus = load("03b_bus_stops_yuseong.csv")
acc = load("05c_traffic_accidents_night_spatial_valid.csv")
police = load("08_police_stations_clean.csv")

targets = hotspots[hotspots["격자취약도순위"].isin([1, 7])].copy()
rows = []
for _, site in targets.iterrows():
    lon, lat = float(site["중심경도"]), float(site["중심위도"])
    dc, dl, db, da, dp = [distances_m(lon, lat, frame) for frame in [cctv, lights, bus, acc, police]]
    rows.append(
        {
            "기존순위": int(site["격자취약도순위"]),
            "후보지": site["인근지역_도로명"],
            "중심경도": lon,
            "중심위도": lat,
            "경계포함비율": site["경계포함비율"],
            "격자내_CCTV수": int(site["CCTV수"]),
            "격자내_가로등수": int(site["가로등수"]),
            "최근접_CCTV거리_m": round(float(np.nanmin(dc)), 1),
            "최근접_가로등거리_m": round(float(np.nanmin(dl)), 1),
            "최근접_경찰기관거리_m": round(float(np.nanmin(dp)), 1),
            "반경250m_CCTV수": int((dc <= 250).sum()),
            "반경250m_가로등수": int((dl <= 250).sum()),
            "반경500m_CCTV수": int((dc <= 500).sum()),
            "반경500m_가로등수": int((dl <= 500).sum()),
            "반경500m_버스정류장수": int((db <= 500).sum()),
            "반경500m_야간사고수": int((da <= 500).sum()),
            "반경1000m_CCTV수": int((dc <= 1000).sum()),
            "반경1000m_가로등수": int((dl <= 1000).sum()),
        }
    )

result = pd.DataFrame(rows)
result.to_csv(ANALYSIS / "06_candidate_site_verification.csv", index=False, encoding="utf-8-sig")
print(result.to_string(index=False))
