import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
path = ROOT / "analysis" / "04_top30_hotspots.csv"
df = pd.read_csv(path, encoding="utf-8-sig").head(10).copy()
labels = []
for _, row in df.iterrows():
    query = urllib.parse.urlencode(
        {
            "lat": f"{row['중심위도']:.7f}",
            "lon": f"{row['중심경도']:.7f}",
            "format": "jsonv2",
            "zoom": 18,
            "addressdetails": 1,
        }
    )
    request = urllib.request.Request(
        "https://nominatim.openstreetmap.org/reverse?" + query,
        headers={"User-Agent": "Codex-Yuseong-Safety-Analysis/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
        address = result.get("address", {})
        road = address.get("road") or address.get("neighbourhood") or address.get("suburb") or ""
        district = address.get("quarter") or address.get("suburb") or address.get("town") or ""
        label = " ".join(part for part in [district, road] if part).strip()
        labels.append(label or result.get("display_name", ""))
    except Exception:
        labels.append("")
    time.sleep(1.05)

df.insert(1, "인근지역_도로명", labels)
df.to_csv(ROOT / "analysis" / "05_top10_hotspot_candidates_labeled.csv", index=False, encoding="utf-8-sig")
print(df[["격자취약도순위", "인근지역_도로명", "격자취약도점수", "버스정류장수", "야간사고수", "CCTV수", "가로등수"]].to_string(index=False))
