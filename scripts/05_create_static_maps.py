"""Create presentation-ready static maps from verified clean datasets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import geopandas as gpd
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1] / "work" / "matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from common import DATA_CLEAN, MAPS, TABLES, configure_korean_font, configure_logging, load_yuseong_boundaries, write_csv


def decorate_axis(ax: Any, boundary: gpd.GeoDataFrame, title: str, note: str = "") -> None:
    """Apply consistent title, north arrow, scale bar, and clean framing."""
    boundary.boundary.plot(ax=ax, color="#334155", linewidth=1.1, zorder=5)
    ax.set_title(title, fontsize=15, fontweight="bold", pad=12)
    ax.annotate("N", xy=(0.96, 0.93), xytext=(0.96, 0.82), xycoords="axes fraction", ha="center", fontsize=11, fontweight="bold", arrowprops={"facecolor": "#111827", "width": 2, "headwidth": 7})
    minx, miny, maxx, maxy = boundary.total_bounds
    scale_length = 5000
    x0 = minx + (maxx - minx) * 0.06
    y0 = miny + (maxy - miny) * 0.06
    ax.plot([x0, x0 + scale_length], [y0, y0], color="#111827", linewidth=3, zorder=10)
    ax.text(x0 + scale_length / 2, y0 + (maxy - miny) * 0.015, "5 km", ha="center", va="bottom", fontsize=8)
    if note:
        ax.text(0.01, 0.01, note, transform=ax.transAxes, fontsize=8, color="#475569", va="bottom", bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none", "pad": 3})
    ax.set_axis_off()


def save_figure(fig: Any, path: Path) -> None:
    """Save at 1600×1000 pixels and 200 dpi."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(pad=0.5)
    fig.savefig(path, dpi=200, facecolor="white")
    plt.close(fig)


def load_points(name: str) -> gpd.GeoDataFrame | None:
    """Load a clean WGS84 GeoJSON and convert it to EPSG:5179."""
    path = DATA_CLEAN / name
    if not path.exists():
        return None
    return gpd.read_file(path).to_crs(epsg=5179)


def create_single_layer_map(boundary: gpd.GeoDataFrame, points: gpd.GeoDataFrame, *, filename: str, title: str, color: str, label: str, size: float, alpha: float) -> tuple[str, int, str]:
    """Create one boundary-plus-point distribution map."""
    fig, ax = plt.subplots(figsize=(8, 5))
    boundary.plot(ax=ax, color="#F8FAFC", edgecolor="#334155", linewidth=1)
    points.plot(ax=ax, color=color, markersize=size, alpha=alpha, label=f"{label} ({len(points):,})", zorder=3)
    decorate_axis(ax, boundary, title, f"표시 건수 {len(points):,} | SGIS 2025년 2분기 유성구 경계")
    ax.legend(loc="upper left", frameon=True, fontsize=8)
    path = MAPS / filename
    save_figure(fig, path)
    return path.name, len(points), "completed"


def create_combined_map(boundary: gpd.GeoDataFrame, cctv: gpd.GeoDataFrame, streetlights: gpd.GeoDataFrame, police: gpd.GeoDataFrame) -> tuple[str, int, str]:
    """Create a verified CCTV, streetlight, and police-facility overlay."""
    fig, ax = plt.subplots(figsize=(8, 5))
    boundary.plot(ax=ax, color="#F8FAFC", edgecolor="#334155", linewidth=1)
    streetlights.plot(ax=ax, color="#2563EB", markersize=1.0, alpha=0.25, label=f"가로등 ({len(streetlights):,})")
    cctv.plot(ax=ax, color="#7C3AED", markersize=10, alpha=0.78, label=f"CCTV 설치지점 ({len(cctv):,})", zorder=3)
    police.plot(ax=ax, color="#DC2626", marker="^", markersize=45, alpha=0.95, label=f"경찰기관 ({len(police):,})")
    decorate_axis(ax, boundary, "유성구 안전시설 현황 중첩도", "행정안전부 전국CCTV표준데이터 사용 | 취약지역 판정 결과가 아닌 현황 지도")
    ax.legend(loc="upper left", fontsize=8, frameon=True)
    path = MAPS / "05_safety_facilities_combined.png"
    save_figure(fig, path)
    return path.name, len(cctv) + len(streetlights) + len(police), "completed"


def create_accident_overlay(boundary: gpd.GeoDataFrame, accidents: gpd.GeoDataFrame, streetlights: gpd.GeoDataFrame, cctv: gpd.GeoDataFrame) -> tuple[str, int, str]:
    """Overlay night accidents, streetlights, and CCTV as a descriptive status map."""
    fig, ax = plt.subplots(figsize=(8, 5))
    boundary.plot(ax=ax, color="#F8FAFC", edgecolor="#334155", linewidth=1)
    streetlights.plot(ax=ax, color="#2563EB", markersize=0.8, alpha=0.16, label=f"가로등 ({len(streetlights):,})")
    cctv.plot(ax=ax, color="#7C3AED", markersize=8, alpha=0.62, label=f"CCTV ({len(cctv):,})", zorder=3)
    accidents.plot(ax=ax, color="#F97316", markersize=7, alpha=0.55, label=f"야간 사고 ({len(accidents):,})")
    decorate_axis(ax, boundary, "유성구 야간 교통사고·안전시설 현황 중첩", "CCTV·가로등·야간사고 현황이며 최종 취약지역 판정이 아님")
    ax.legend(loc="upper left", fontsize=8, frameon=True)
    path = MAPS / "06_night_accidents_and_facilities.png"
    save_figure(fig, path)
    return path.name, len(accidents) + len(streetlights) + len(cctv), "completed"


def create_population_or_floating_map(boundary: gpd.GeoDataFrame, dong: gpd.GeoDataFrame) -> tuple[str, int, str]:
    """Prefer a floating-population choropleth and fall back to elderly ratio."""
    name_column = "ADM_NM" if "ADM_NM" in dong.columns else next(column for column in dong.columns if "NM" in str(column).upper())
    floating_path = DATA_CLEAN / "06_floating_population_by_dong_summary.csv"
    if floating_path.exists():
        floating = pd.read_csv(floating_path, encoding="utf-8-sig")
        merged = dong.merge(floating, left_on=name_column, right_on="행정동", how="left")
        merged["floating_population_thousands"] = merged["daily_average_2023"].div(1000)
        value_column = "floating_population_thousands"
        title = "유성구 행정동별 2023년 일평균 유동인구 (천 명)"
        note = "2023년 1~12월 월별 일평균의 평균"
    else:
        population_path = DATA_CLEAN / "07_population_by_dong_summary.csv"
        population = pd.read_csv(population_path, encoding="utf-8-sig")
        merged = dong.merge(population, left_on=name_column, right_on="행정동이름", how="left")
        value_column = "elderly_ratio"
        title = "유성구 행정동별 65세 이상 인구 비율"
        note = "유동인구 미확보 시 2022-01 고령인구 비율로 대체"
    matched = int(merged[value_column].notna().sum())
    fig, ax = plt.subplots(figsize=(8, 5))
    merged.plot(column=value_column, ax=ax, cmap="YlOrRd", edgecolor="white", linewidth=0.7, legend=True, missing_kwds={"color": "#E2E8F0", "label": "미결합"}, legend_kwds={"shrink": 0.82})
    decorate_axis(ax, boundary, title, f"{note} | 경계 결합 {matched}/{len(dong)}개 행정동")
    path = MAPS / "07_population_or_floating_population_by_dong.png"
    save_figure(fig, path)
    return path.name, matched, "completed" if matched == len(dong) else "needs_review"


def main() -> None:
    """Create all available static maps and a generation-status table."""
    logger = configure_logging("maps")
    font = configure_korean_font()
    if not font:
        logger.warning("한글 폰트를 자동 탐색하지 못했습니다.")
    boundary, dong = load_yuseong_boundaries()
    cctv = load_points("01_cctv_yuseong_standard.geojson")
    streetlights = load_points("02_streetlights_yuseong.geojson")
    buses = load_points("03_bus_stops_yuseong.geojson")
    accidents = load_points("05_traffic_accidents_night.geojson")
    police = load_points("08_police_stations_clean.geojson")
    rows: list[dict[str, object]] = []

    if cctv is not None:
        result = create_single_layer_map(boundary, cctv, filename="01_cctv_distribution.png", title="유성구 CCTV 설치지점 분포도", color="#7C3AED", label="CCTV 설치지점", size=10, alpha=0.75)
        rows.append(dict(zip(("map_file", "displayed_features", "status"), result)))
    if streetlights is not None:
        result = create_single_layer_map(boundary, streetlights, filename="02_streetlights_distribution.png", title="유성구 가로등 분포도", color="#2563EB", label="가로등", size=1.1, alpha=0.28)
        rows.append(dict(zip(("map_file", "displayed_features", "status"), result)))
    if buses is not None:
        result = create_single_layer_map(boundary, buses, filename="03_bus_stops_distribution.png", title="유성구 버스정류장 분포도", color="#16A34A", label="버스정류장", size=7, alpha=0.7)
        rows.append(dict(zip(("map_file", "displayed_features", "status"), result)))
    if accidents is not None:
        result = create_single_layer_map(boundary, accidents, filename="04_night_traffic_accidents.png", title="유성구 야간 교통사고 분포도 (20:00~06:00)", color="#F97316", label="야간 사고", size=7, alpha=0.55)
        rows.append(dict(zip(("map_file", "displayed_features", "status"), result)))
    if cctv is not None and streetlights is not None and police is not None:
        result = create_combined_map(boundary, cctv, streetlights, police)
        rows.append(dict(zip(("map_file", "displayed_features", "status"), result)))
    if accidents is not None and streetlights is not None and cctv is not None:
        result = create_accident_overlay(boundary, accidents, streetlights, cctv)
        rows.append(dict(zip(("map_file", "displayed_features", "status"), result)))
    result = create_population_or_floating_map(boundary, dong)
    rows.append(dict(zip(("map_file", "displayed_features", "status"), result)))
    write_csv(pd.DataFrame(rows), TABLES / "map_generation_status.csv")
    logger.info("정적 지도 %d개 생성", len(rows))


if __name__ == "__main__":
    main()
