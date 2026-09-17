from __future__ import annotations

import io
import os
import sqlite3
import sys
import zipfile
from calendar import monthrange
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data_raw" / "new_sources_20260917"
CLEAN = ROOT / "data_clean"
SOURCE_DIR = Path(os.environ.get("YUSEONG_FLOW_SOURCE_DIR", "유성구_유동인구_2508-2607"))
PARQUET = SOURCE_DIR / "yuseonggu_night_population_202508_202607.parquet"
GRID = SOURCE_DIR / "yuseonggu_50m_grid_master.gpkg"

sys.path.insert(0, str(ROOT.parents[1] / "work" / "parquet_runtime"))
import pandas as pd
import pyarrow.dataset as ds


def read_cp949_csv(path: Path, dtype: dict[str, str] | None = None) -> pd.DataFrame:
    return pd.read_csv(path, encoding="cp949", dtype=dtype)


def clean_public_files() -> dict[str, int]:
    counts: dict[str, int] = {}

    lights = read_cp949_csv(
        RAW / "15111161.csv",
        dtype={"시도코드": "string", "시군구코드": "string", "행정동코드": "string", "법정동코드": "string"},
    )
    lights.columns = lights.columns.str.strip()
    for c in ["보안등수", "인구수", "보안등비율(퍼센트)"]:
        lights[c] = pd.to_numeric(lights[c], errors="coerce")
    lights["보안등_인구1천명당"] = (lights["보안등수"] / lights["인구수"] * 1000).round(3)
    lights["제공비율_재계산차이"] = (lights["보안등비율(퍼센트)"] - lights["보안등수"] / lights["인구수"] * 100).round(4)
    lights = lights.sort_values(["행정동이름", "법정동이름"], kind="stable")
    out = CLEAN / "10_security_lights_population_by_legal_dong.csv"
    lights.to_csv(out, index=False, encoding="utf-8-sig")
    counts[out.name] = len(lights)

    bus = read_cp949_csv(RAW / "15023415.csv", dtype={"정류장 관리번호": "string", "버스번호": "string"})
    bus.columns = bus.columns.str.strip()
    bus["위도"] = pd.to_numeric(bus["위도"], errors="coerce")
    bus["경도"] = pd.to_numeric(bus["경도"], errors="coerce")
    bus["좌표유효여부"] = bus["위도"].between(36.0, 36.6) & bus["경도"].between(127.0, 127.7)
    bus = bus.drop_duplicates().sort_values(["정류장 관리번호", "버스번호", "방향"], kind="stable")
    route_out = CLEAN / "12_village_bus_stop_routes_clean.csv"
    bus.to_csv(route_out, index=False, encoding="utf-8-sig")
    counts[route_out.name] = len(bus)

    valid_bus = bus.loc[bus["좌표유효여부"]].copy()
    stops = (
        valid_bus.groupby(["정류장 관리번호", "정류장명", "위도", "경도"], dropna=False)
        .agg(
            노선수=("버스번호", "nunique"),
            노선목록=("버스번호", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
            방향목록=("방향", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
        )
        .reset_index()
        .sort_values("정류장 관리번호", kind="stable")
    )
    stop_out = CLEAN / "12b_village_bus_stops_unique.csv"
    stops.to_csv(stop_out, index=False, encoding="utf-8-sig")
    counts[stop_out.name] = len(stops)

    bells = read_cp949_csv(
        RAW / "15108941.csv",
        dtype={"관리번호": "string", "시도코드": "string", "시군구코드": "string", "행정동코드": "string", "법정동코드": "string"},
    )
    bells.columns = bells.columns.str.strip()
    bells["위도"] = pd.to_numeric(bells["위도"], errors="coerce")
    bells["경도"] = pd.to_numeric(bells["경도"], errors="coerce")
    bells["좌표유효여부"] = bells["위도"].between(36.0, 36.6) & bells["경도"].between(127.0, 127.7)
    bells["표시위치"] = bells["설치위치"].fillna("").str.strip()
    bells.loc[bells["표시위치"].eq(""), "표시위치"] = bells["주소"]
    bells = bells.drop_duplicates(subset=["관리번호"], keep="first").sort_values("관리번호", kind="stable")
    bell_out = CLEAN / "13_emergency_bells_point_clean.csv"
    bells.to_csv(bell_out, index=False, encoding="utf-8-sig")
    counts[bell_out.name] = len(bells)

    frames = []
    with zipfile.ZipFile(RAW / "15098232.zip") as archive:
        for name in archive.namelist():
            payload = archive.read(name)
            decoded = None
            for encoding in ("utf-8-sig", "cp949"):
                try:
                    decoded = payload.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if decoded is None:
                raise UnicodeError(f"Cannot decode {name}")
            frame = pd.read_csv(io.StringIO(decoded), dtype={"법정동코드": "string", "기준월": "string"})
            frames.append(frame)
    flow = pd.concat(frames, ignore_index=True)
    flow.columns = flow.columns.str.strip()
    flow["기준월"] = flow["기준월"].str.zfill(2)
    flow["기준년월"] = flow["기준년도"].astype("Int64").astype("string") + "-" + flow["기준월"]
    flow["일평균유동인구"] = pd.to_numeric(flow["일평균유동인구"], errors="coerce")
    flow["원자료_법정동누락"] = flow["법정동코드"].isna() | flow["법정동명"].isna()
    flow["법정동코드"] = flow["법정동코드"].fillna("미상")
    flow["법정동명"] = flow["법정동명"].fillna("미상(원자료 누락)")
    flow = flow[["기준년월", "기준년도", "기준월", "법정동코드", "법정동명", "시간대", "일평균유동인구", "원자료_법정동누락"]]
    flow = flow.drop_duplicates().sort_values(["기준년월", "법정동코드", "시간대"], kind="stable")
    flow_out = CLEAN / "11_floating_population_legal_dong_2020_2022.csv"
    flow.to_csv(flow_out, index=False, encoding="utf-8-sig")
    counts[flow_out.name] = len(flow)

    return counts


def aggregate_private_population() -> dict[str, int]:
    con = sqlite3.connect(GRID)
    grid = pd.read_sql_query("SELECT celno, xaxs_crdnt, yaxs_crdnt FROM grid_master", con)
    con.close()
    x0 = float(grid["xaxs_crdnt"].min()) - 25.0
    y0 = float(grid["yaxs_crdnt"].min()) - 25.0
    grid["grid_col"] = ((grid["xaxs_crdnt"] - x0) // 500).astype("int32")
    grid["grid_row"] = ((grid["yaxs_crdnt"] - y0) // 500).astype("int32")
    grid["grid500_id"] = "G" + grid["grid_col"].astype(str).str.zfill(3) + "_" + grid["grid_row"].astype(str).str.zfill(3)
    cell_to_grid = dict(zip(grid["celno"].astype(int), grid["grid500_id"]))
    grid_meta = grid.groupby("grid500_id", as_index=False).agg(
        grid_col=("grid_col", "first"), grid_row=("grid_row", "first")
    )
    grid_meta["center_x_epsg5179"] = x0 + grid_meta["grid_col"] * 500 + 250
    grid_meta["center_y_epsg5179"] = y0 + grid_meta["grid_row"] * 500 + 250

    totals: pd.DataFrame | None = None
    active_pairs: list[pd.DataFrame] = []
    dataset = ds.dataset(PARQUET, format="parquet")
    scanner = dataset.scanner(columns=["de", "celno", "h_pop", "w_pop", "v_pop"], batch_size=500_000)
    for idx, batch in enumerate(scanner.to_batches(), start=1):
        part = batch.to_pandas()
        part["month"] = (part["de"] // 100).astype("int32")
        part["grid500_id"] = part["celno"].map(cell_to_grid)
        if part["grid500_id"].isna().any():
            raise ValueError("Population record references a missing grid cell")
        grouped = part.groupby(["month", "grid500_id"], as_index=False).agg(
            h_sum=("h_pop", "sum"), w_sum=("w_pop", "sum"), v_sum=("v_pop", "sum"), source_rows=("celno", "size")
        )
        totals = grouped if totals is None else pd.concat([totals, grouped], ignore_index=True).groupby(
            ["month", "grid500_id"], as_index=False
        ).sum()
        active_pairs.append(part[["month", "grid500_id", "celno"]].drop_duplicates())
        if idx % 25 == 0:
            print(f"processed batches: {idx}", flush=True)

    assert totals is not None
    active = pd.concat(active_pairs, ignore_index=True).drop_duplicates()
    active = active.groupby(["month", "grid500_id"], as_index=False).agg(active_50m_cells=("celno", "size"))
    monthly = totals.merge(active, on=["month", "grid500_id"], how="left").merge(grid_meta, on="grid500_id", how="left")
    monthly["year"] = monthly["month"] // 100
    monthly["month_num"] = monthly["month"] % 100
    monthly["days_in_month"] = [monthrange(int(y), int(m))[1] for y, m in zip(monthly["year"], monthly["month_num"])]
    monthly["expected_time_slots"] = monthly["days_in_month"] * 9
    for src, dst in [("h_sum", "avg_home_pop"), ("w_sum", "avg_work_pop"), ("v_sum", "avg_visit_pop")]:
        monthly[dst] = monthly[src] / monthly["expected_time_slots"]
    monthly["avg_total_pop"] = monthly[["avg_home_pop", "avg_work_pop", "avg_visit_pop"]].sum(axis=1)
    monthly["source_coverage_pct"] = monthly["source_rows"] / (monthly["active_50m_cells"] * monthly["expected_time_slots"]) * 100
    monthly["period"] = monthly["year"].astype(str) + "-" + monthly["month_num"].astype(str).str.zfill(2)
    monthly["privacy_rule"] = "500m aggregation; at least 4 contributing 50m cells"
    monthly = monthly.loc[monthly["active_50m_cells"] >= 4].copy()
    numeric_round = ["avg_home_pop", "avg_work_pop", "avg_visit_pop", "avg_total_pop", "source_coverage_pct"]
    monthly[numeric_round] = monthly[numeric_round].round(2)
    monthly = monthly[[
        "period", "grid500_id", "center_x_epsg5179", "center_y_epsg5179", "active_50m_cells", "source_rows",
        "expected_time_slots", "source_coverage_pct", "avg_home_pop", "avg_work_pop", "avg_visit_pop", "avg_total_pop", "privacy_rule"
    ]].sort_values(["period", "grid500_id"], kind="stable")
    month_out = CLEAN / "14_night_population_500m_monthly_202508_202607.csv"
    monthly.to_csv(month_out, index=False, encoding="utf-8-sig")

    for c in ["avg_home_pop", "avg_work_pop", "avg_visit_pop", "avg_total_pop"]:
        monthly[f"weighted_{c}"] = monthly[c] * monthly["expected_time_slots"]
    annual = monthly.groupby("grid500_id", as_index=False).agg(
        center_x_epsg5179=("center_x_epsg5179", "first"),
        center_y_epsg5179=("center_y_epsg5179", "first"),
        months_present=("period", "nunique"),
        min_active_50m_cells=("active_50m_cells", "min"),
        total_time_slots=("expected_time_slots", "sum"),
        weighted_avg_home_pop=("weighted_avg_home_pop", "sum"),
        weighted_avg_work_pop=("weighted_avg_work_pop", "sum"),
        weighted_avg_visit_pop=("weighted_avg_visit_pop", "sum"),
        weighted_avg_total_pop=("weighted_avg_total_pop", "sum"),
        avg_source_coverage_pct=("source_coverage_pct", "mean"),
    )
    for c in ["home", "work", "visit", "total"]:
        annual[f"avg_{c}_pop"] = annual.pop(f"weighted_avg_{c}_pop") / annual["total_time_slots"]
    annual["privacy_rule"] = "500m aggregation; monthly cells with fewer than 4 contributing 50m cells excluded"
    for c in ["avg_home_pop", "avg_work_pop", "avg_visit_pop", "avg_total_pop", "avg_source_coverage_pct"]:
        annual[c] = annual[c].round(2)
    annual = annual.sort_values("grid500_id", kind="stable")
    annual_out = CLEAN / "14b_night_population_500m_period_average.csv"
    annual.to_csv(annual_out, index=False, encoding="utf-8-sig")
    return {month_out.name: len(monthly), annual_out.name: len(annual)}


if __name__ == "__main__":
    print("public", clean_public_files(), flush=True)
    print("population", aggregate_private_population(), flush=True)
