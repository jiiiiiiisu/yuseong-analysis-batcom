from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data_raw"
CLEAN = ROOT / "data_clean"
CLEAN.mkdir(exist_ok=True)


def read_raw(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW / name, encoding="cp949", low_memory=False)


def save_clean(df: pd.DataFrame, name: str) -> None:
    df.to_csv(CLEAN / name, index=False, encoding="utf-8-sig")


def number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def inverse_epsg5179(x_values: pd.Series, y_values: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Inverse Korea 2000 / Unified CS (EPSG:5179) to geographic coordinates.

    EPSG:5179 uses the GRS80 ellipsoid and a Transverse Mercator projection.
    Geographic output is effectively WGS84 for this local analysis.
    """
    a = 6378137.0
    inv_f = 298.257222101
    f = 1.0 / inv_f
    e2 = f * (2.0 - f)
    ep2 = e2 / (1.0 - e2)
    k0 = 0.9996
    lon0 = math.radians(127.5)
    lat0 = math.radians(38.0)
    false_easting = 1_000_000.0
    false_northing = 2_000_000.0

    def meridional_arc(phi: float) -> float:
        return a * (
            (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * phi
            - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * phi)
            + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * phi)
            - (35 * e2**3 / 3072) * math.sin(6 * phi)
        )

    m0 = meridional_arc(lat0)
    xs = number(x_values).to_numpy(dtype=float)
    ys = number(y_values).to_numpy(dtype=float)
    lons = np.full(len(xs), np.nan)
    lats = np.full(len(xs), np.nan)

    for i, (x, y) in enumerate(zip(xs, ys)):
        if not np.isfinite(x) or not np.isfinite(y):
            continue
        m = m0 + (y - false_northing) / k0
        mu = m / (a * (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256))
        e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
        phi1 = (
            mu
            + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu)
            + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu)
            + (151 * e1**3 / 96) * math.sin(6 * mu)
            + (1097 * e1**4 / 512) * math.sin(8 * mu)
        )
        n1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
        r1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
        t1 = math.tan(phi1) ** 2
        c1 = ep2 * math.cos(phi1) ** 2
        d = (x - false_easting) / (n1 * k0)
        lat = phi1 - (n1 * math.tan(phi1) / r1) * (
            d**2 / 2
            - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ep2) * d**4 / 24
            + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ep2 - 3 * c1**2) * d**6 / 720
        )
        lon = lon0 + (
            d
            - (1 + 2 * t1 + c1) * d**3 / 6
            + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ep2 + 24 * t1**2) * d**5 / 120
        ) / math.cos(phi1)
        lons[i] = math.degrees(lon)
        lats[i] = math.degrees(lat)
    return lons, lats


def fit_local_xy_to_wgs84(police: pd.DataFrame):
    """Fit a local affine transform using police-station control points.

    CCTV and police files share the same local X/Y value range. The police file
    also contains geographic coordinates, allowing a transparent local fit.
    """
    controls = police.copy()
    x = number(controls["X좌표"])
    y = number(controls["Y좌표"])
    lon = number(controls["위도"])  # Source file labels longitude as latitude.
    lat = number(controls["경도"])  # Source file labels latitude as longitude.
    valid = x.notna() & y.notna() & lon.notna() & lat.notna()
    matrix = np.column_stack([np.ones(valid.sum()), x[valid], y[valid]])
    lon_coef = np.linalg.lstsq(matrix, lon[valid], rcond=None)[0]
    lat_coef = np.linalg.lstsq(matrix, lat[valid], rcond=None)[0]
    return lon_coef, lat_coef


def apply_affine(x_values: pd.Series, y_values: pd.Series, coef: np.ndarray) -> np.ndarray:
    x = number(x_values).to_numpy(dtype=float)
    y = number(y_values).to_numpy(dtype=float)
    return coef[0] + coef[1] * x + coef[2] * y


qc: list[dict[str, object]] = []


def record(name: str, source_rows: int, output: pd.DataFrame, note: str = "") -> None:
    qc.append(
        {
            "데이터": name,
            "원본행수": source_rows,
            "정제행수": len(output),
            "결측_경도": int(output["경도_WGS84"].isna().sum()) if "경도_WGS84" in output else "",
            "결측_위도": int(output["위도_WGS84"].isna().sum()) if "위도_WGS84" in output else "",
            "비고": note,
        }
    )


# Police stations: source geographic coordinate labels are reversed.
police_raw = read_raw("08_police_stations.csv")
police = police_raw.copy()
police["경도_WGS84"] = number(police_raw["위도"])
police["위도_WGS84"] = number(police_raw["경도"])
save_clean(police, "08_police_stations_clean.csv")
record("경찰기관", len(police_raw), police, "원본 위도·경도 표기가 반대여서 교정")


# CCTV: transform local X/Y using police-station control points.
lon_coef, lat_coef = fit_local_xy_to_wgs84(police_raw)
cctv_raw = read_raw("01_cctv.csv")
cctv = cctv_raw.copy()
cctv["X좌표_원본"] = number(cctv_raw["위도"])
cctv["Y좌표_원본"] = number(cctv_raw["경도"])
cctv["경도_WGS84"] = apply_affine(cctv["X좌표_원본"], cctv["Y좌표_원본"], lon_coef)
cctv["위도_WGS84"] = apply_affine(cctv["X좌표_원본"], cctv["Y좌표_원본"], lat_coef)
save_clean(cctv, "01_cctv_clean.csv")
record("CCTV", len(cctv_raw), cctv, "경찰기관의 X/Y-WGS84 대응점을 이용한 유성구 지역 보정")


# Streetlights: filter the Daejeon-wide file to Yuseong-gu.
street_raw = read_raw("02_streetlights.csv")
street = street_raw[street_raw["행정읍면동"].astype(str).str.contains("유성구", na=False)].copy()
street["경도_WGS84"] = number(street["경도"])
street["위도_WGS84"] = number(street["위도"])
save_clean(street, "02_streetlights_yuseong.csv")
record("가로등", len(street_raw), street, "행정읍면동에서 유성구 필터링")


# Bus stops: keep Daejeon first; a Yuseong boundary polygon is needed for an exact district clip.
bus_raw = read_raw("03_bus_stops.csv")
bus = bus_raw[bus_raw["도시명"].astype(str).str.contains("대전", na=False)].copy()
bus["경도_WGS84"] = number(bus["경도"])
bus["위도_WGS84"] = number(bus["위도"])
bus_swap = bus["경도_WGS84"].between(33, 39) & bus["위도_WGS84"].between(126, 130)
bus.loc[bus_swap, ["경도_WGS84", "위도_WGS84"]] = bus.loc[bus_swap, ["위도_WGS84", "경도_WGS84"]].to_numpy()
bus["좌표유효여부"] = bus["경도_WGS84"].between(126, 130) & bus["위도_WGS84"].between(33, 39)
save_clean(bus, "03_bus_stops_daejeon.csv")
record("버스정류장", len(bus_raw), bus, f"대전광역시 필터링; 역전좌표 {int(bus_swap.sum())}건 교정; 유성구 경계 공간필터 필요")


# Emergency bells: aggregate legal-dong rows to administrative dongs.
bells_raw = read_raw("04_emergency_bells_by_dong.csv")
for col in ["비상벨수", "인구수"]:
    bells_raw[col] = number(bells_raw[col]).fillna(0)
bells = (
    bells_raw.groupby(["기준년도", "행정동코드", "행정동이름"], dropna=False, as_index=False)
    .agg(비상벨수=("비상벨수", "sum"), 인구수=("인구수", "sum"), 포함법정동수=("법정동이름", "nunique"))
)
bells["인구1만명당_비상벨수"] = np.where(bells["인구수"] > 0, bells["비상벨수"] / bells["인구수"] * 10000, np.nan)
save_clean(bells, "04_emergency_bells_admin_dong.csv")
record("비상벨", len(bells_raw), bells, "법정동 자료를 행정동 단위로 합산")


# Traffic accidents: transform EPSG:5179 X/Y, parse time, and flag nighttime.
acc_raw = read_raw("05_traffic_accidents.csv")
acc = acc_raw.copy()
acc["X좌표_원본"] = number(acc_raw["위도"])
acc["Y좌표_원본"] = number(acc_raw["경도"])
acc["경도_WGS84"], acc["위도_WGS84"] = inverse_epsg5179(acc["X좌표_원본"], acc["Y좌표_원본"])
acc["발생일시_표준"] = pd.to_datetime(acc["발생일시"], errors="coerce")
acc["발생시각"] = acc["발생일시_표준"].dt.hour
acc["야간여부_20시_06시"] = ((acc["발생시각"] >= 20) | (acc["발생시각"] < 6)).astype("Int64")
acc["유성구근사범위여부"] = acc["경도_WGS84"].between(127.15, 127.50) & acc["위도_WGS84"].between(36.20, 36.55)
save_clean(acc, "05_traffic_accidents_clean.csv")
night_acc = acc[acc["야간여부_20시_06시"] == 1].copy()
save_clean(night_acc, "05b_traffic_accidents_night.csv")
night_acc_valid = night_acc[night_acc["유성구근사범위여부"]].copy()
save_clean(night_acc_valid, "05c_traffic_accidents_night_spatial_valid.csv")
record("교통사고", len(acc_raw), acc, f"EPSG:5179 변환; 야간 {len(night_acc):,}건 중 공간범위 유효 {len(night_acc_valid):,}건")


# Monthly floating population files.
flow_parts = []
for path in sorted((RAW / "06_floating_population_monthly").glob("*.csv")):
    part = pd.read_csv(path, encoding="cp949")
    month_match = re.search(r"(\d+)월", path.stem)
    part["기준년도"] = 2023
    part["기준월"] = int(month_match.group(1)) if month_match else number(part["월"])
    part["일평균유동인구"] = number(part["일평균"])
    flow_parts.append(part[["기준년도", "기준월", "행정동", "일평균유동인구"]])
flow = pd.concat(flow_parts, ignore_index=True).sort_values(["기준월", "행정동"])
save_clean(flow, "06_floating_population_admin_dong_monthly.csv")
flow_annual = (
    flow.groupby("행정동", as_index=False)
    .agg(연평균_일평균유동인구=("일평균유동인구", "mean"), 포함월수=("기준월", "nunique"))
)
save_clean(flow_annual, "06b_floating_population_admin_dong_annual.csv")
record("유동인구", len(flow), flow, "월별 12개 파일을 통합하고 행정동별 연평균 산출")


# Population: use the latest snapshot, then aggregate age/sex measures by administrative dong.
pop_raw = read_raw("07_population_sex_age_by_dong.csv")
pop_raw["기준년월_표준"] = pd.to_datetime(pop_raw["기준년월"], format="%b-%y", errors="coerce")
latest_month = pop_raw["기준년월_표준"].max()
pop_latest = pop_raw[
    (pop_raw["기준년월_표준"] == latest_month)
    & pop_raw["행정동코드"].notna()
    & pop_raw["행정동이름"].notna()
].copy()
pop_latest["연령_숫자"] = number(pop_latest["연령"])
pop_latest["인구수_숫자"] = number(pop_latest["인구수"]).fillna(0)

def summarize_population(group: pd.DataFrame) -> pd.Series:
    total = group["인구수_숫자"].sum()
    female = group.loc[group["성별"].eq("여"), "인구수_숫자"].sum()
    elderly = group.loc[group["연령_숫자"].ge(65), "인구수_숫자"].sum()
    youth = group.loc[group["연령_숫자"].lt(18), "인구수_숫자"].sum()
    return pd.Series(
        {
            "총인구": total,
            "여성인구": female,
            "65세이상인구": elderly,
            "18세미만인구": youth,
            "여성비율": female / total if total else np.nan,
            "고령인구비율": elderly / total if total else np.nan,
            "아동청소년비율": youth / total if total else np.nan,
        }
    )

pop = (
    pop_latest.groupby(["행정동코드", "행정동이름"], dropna=False)
    .apply(summarize_population, include_groups=False)
    .reset_index()
)
pop.insert(0, "기준년월", latest_month.strftime("%Y-%m") if pd.notna(latest_month) else "")
save_clean(pop, "07_population_latest_admin_dong.csv")
record("성연령별 인구", len(pop_raw), pop, f"최신 기준월 {pop.iloc[0]['기준년월'] if len(pop) else '확인불가'} 집계")


# Administrative-dong base table for the first-stage demand analysis.
base = pop.merge(flow_annual, left_on="행정동이름", right_on="행정동", how="outer")
base["행정동이름"] = base["행정동이름"].fillna(base["행정동"])
base = base.drop(columns=["행정동"], errors="ignore")
base = base.merge(bells.drop(columns=["기준년도", "인구수"], errors="ignore"), on=["행정동코드", "행정동이름"], how="left")
cctv_by_dong = cctv.groupby(["행정동코드", "행정동이름"], dropna=False, as_index=False).agg(CCTV지점수=("관리번호", "count"), 카메라대수=("카메라대수", "sum"))
base = base.merge(cctv_by_dong, on=["행정동코드", "행정동이름"], how="left")
acc_by_dong = acc.groupby(["행정동코드", "행정동이름"], dropna=False, as_index=False).agg(교통사고수=("사고번호", "count"), 야간교통사고수=("야간여부_20시_06시", "sum"))
base = base.merge(acc_by_dong, on=["행정동코드", "행정동이름"], how="left")
for col in ["비상벨수", "CCTV지점수", "카메라대수", "교통사고수", "야간교통사고수"]:
    if col in base:
        base[col] = base[col].fillna(0)
base["인구1만명당_CCTV지점수"] = np.where(base["총인구"] > 0, base["CCTV지점수"] / base["총인구"] * 10000, np.nan)
base["인구1만명당_야간교통사고수_2017_2021누적"] = np.where(base["총인구"] > 0, base["야간교통사고수"] / base["총인구"] * 10000, np.nan)
save_clean(base.sort_values("행정동이름"), "09_admin_dong_base_table.csv")


qc_df = pd.DataFrame(qc)
save_clean(qc_df, "00_quality_check.csv")
print(qc_df.to_string(index=False))
print(f"행정동 기초표: {len(base)}행, {len(base.columns)}열")

for label, frame in [("CCTV", cctv), ("가로등", street), ("대전 버스정류장", bus), ("교통사고", acc), ("경찰기관", police)]:
    print(
        f"{label} 좌표범위: "
        f"경도 {frame['경도_WGS84'].min():.6f}~{frame['경도_WGS84'].max():.6f}, "
        f"위도 {frame['위도_WGS84'].min():.6f}~{frame['위도_WGS84'].max():.6f}"
    )

print("행정동 기초표 주요 결측:")
for col in ["총인구", "연평균_일평균유동인구", "비상벨수", "CCTV지점수", "야간교통사고수"]:
    print(f"  {col}: {int(base[col].isna().sum()) if col in base else '컬럼없음'}")
