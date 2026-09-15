"""Preprocess point datasets using the inspected source columns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from common import (
    DATA_CLEAN,
    DATA_RAW,
    TABLES,
    configure_logging,
    load_yuseong_boundaries,
    read_csv_safely,
    write_csv,
)


def canonicalize_points(
    frame: pd.DataFrame, x_column: str, y_column: str, source_crs: str
) -> tuple[gpd.GeoDataFrame, int, int]:
    """Build WGS84 points and canonical EPSG:5179/WGS84 coordinate columns."""
    working = frame.copy()
    working[x_column] = pd.to_numeric(working[x_column], errors="coerce")
    working[y_column] = pd.to_numeric(working[y_column], errors="coerce")
    missing_coordinates = int(working[[x_column, y_column]].isna().any(axis=1).sum())
    working = working.dropna(subset=[x_column, y_column]).copy()
    source = gpd.GeoDataFrame(
        working,
        geometry=gpd.points_from_xy(working[x_column], working[y_column]),
        crs=source_crs,
    )
    metric = source.to_crs(epsg=5179)
    wgs84 = source.to_crs(epsg=4326)
    wgs84["x_5179"] = metric.geometry.x.to_numpy()
    wgs84["y_5179"] = metric.geometry.y.to_numpy()
    wgs84["longitude"] = wgs84.geometry.x
    wgs84["latitude"] = wgs84.geometry.y
    valid = wgs84["longitude"].between(124, 132) & wgs84["latitude"].between(33, 39)
    invalid_coordinates = int((~valid).sum())
    return wgs84.loc[valid].copy(), missing_coordinates, invalid_coordinates


def spatial_filter(points: gpd.GeoDataFrame, yuseong: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep points strictly inside the official Yuseong sigungu boundary."""
    union = yuseong.to_crs(points.crs).geometry.union_all()
    return points[points.geometry.within(union)].copy()


def save_points(points: gpd.GeoDataFrame, csv_path: Path, geojson_path: Path) -> None:
    """Save canonical point data as UTF-8 CSV and WGS84 GeoJSON."""
    write_csv(pd.DataFrame(points.drop(columns="geometry")), csv_path)
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    points.to_crs(epsg=4326).to_file(geojson_path, driver="GeoJSON")


def summary_row(
    dataset: str,
    original_rows: int,
    filtered_rows: int,
    missing_coordinates: int,
    duplicates_removed: int,
    invalid_coordinates: int,
    output_file: Path,
    status: str = "completed",
    notes: str = "",
) -> dict[str, Any]:
    """Build one consistent preprocessing-summary row."""
    return {
        "dataset": dataset,
        "original_rows": original_rows,
        "filtered_rows": filtered_rows,
        "missing_coordinate_rows": missing_coordinates,
        "duplicate_rows_removed": duplicates_removed,
        "invalid_coordinate_rows": invalid_coordinates,
        "output_file": str(output_file.relative_to(DATA_CLEAN.parent)),
        "status": status,
        "notes": notes,
    }


def process_cctv(yuseong: gpd.GeoDataFrame, logger: Any) -> dict[str, Any]:
    """Filter the nationwide-standard WGS84 CCTV data and validate the Yuseong boundary."""
    source = DATA_RAW / "01_cctv" / "01_cctv_national_standard_yuseong.csv"
    frame, encoding = read_csv_safely(source, dtype={"관리번호": "string"})
    before = len(frame)
    address = frame["소재지도로명주소"].fillna("") + " " + frame["소재지지번주소"].fillna("")
    candidates = frame[address.str.contains("유성구", na=False)].copy()
    duplicates = int(candidates.duplicated().sum())
    candidates = candidates.drop_duplicates().copy()
    candidate_points, missing, invalid = canonicalize_points(
        candidates, "WGS84경도", "WGS84위도", "EPSG:4326"
    )
    points = spatial_filter(candidate_points, yuseong)
    out_of_boundary = len(candidate_points) - len(points)
    csv_path = DATA_CLEAN / "01_cctv_yuseong_standard.csv"
    save_points(points, csv_path, DATA_CLEAN / "01_cctv_yuseong_standard.geojson")
    camera_total = int(pd.to_numeric(points["카메라대수"], errors="coerce").fillna(0).sum())
    logger.info(
        "CCTV 전국표준: %d -> 주소 %d -> 경계 %d지점/%d대, %s",
        before,
        len(candidates),
        len(points),
        camera_total,
        encoding,
    )
    return summary_row(
        "CCTV",
        before,
        len(points),
        missing,
        duplicates,
        invalid + out_of_boundary,
        csv_path,
        notes=(
            f"행정안전부 전국표준 WGS84; 유성구 주소 {len(candidates):,}건 중 "
            f"공식 경계 내부 {len(points):,}지점·카메라 {camera_total:,}대"
        ),
    )


def process_streetlights(yuseong: gpd.GeoDataFrame, logger: Any) -> dict[str, Any]:
    """Filter Daejeon streetlights to Yuseong by admin text and official boundary."""
    source = DATA_RAW / "02_streetlights" / "02_streetlights.csv"
    frame, encoding = read_csv_safely(source)
    before = len(frame)
    candidates = frame[
        frame["행정읍면동"].astype("string").str.contains("유성구", na=False)
    ].copy()
    duplicates = int(candidates.duplicated().sum())
    candidates = candidates.drop_duplicates().copy()
    points, missing, invalid = canonicalize_points(candidates, "경도", "위도", "EPSG:4326")
    points = spatial_filter(points, yuseong)
    csv_path = DATA_CLEAN / "02_streetlights_yuseong.csv"
    save_points(points, csv_path, DATA_CLEAN / "02_streetlights_yuseong.geojson")
    logger.info("가로등: %d -> 텍스트 %d -> 경계 %d, %s", before, len(candidates), len(points), encoding)
    return summary_row("가로등", before, len(points), missing, duplicates, invalid, csv_path, notes=f"행정읍면동 유성구 1차 필터 {len(candidates):,}건 후 공식 경계 재검증")


def process_bus_stops(yuseong: gpd.GeoDataFrame, logger: Any) -> dict[str, Any]:
    """Reduce nationwide bus stops to Daejeon, then spatially filter to Yuseong."""
    source = DATA_RAW / "03_bus_stops" / "03_bus_stops.csv"
    frame, encoding = read_csv_safely(source, dtype={"정류장번호": "string"})
    before = len(frame)
    daejeon = frame[
        frame["도시명"].astype("string").str.contains("대전", na=False)
        | frame["관리도시명"].astype("string").str.contains("대전", na=False)
    ].copy()
    duplicates = int(daejeon.duplicated().sum())
    daejeon = daejeon.drop_duplicates().copy()
    points, missing, invalid = canonicalize_points(daejeon, "경도", "위도", "EPSG:4326")
    points = spatial_filter(points, yuseong)
    csv_path = DATA_CLEAN / "03_bus_stops_yuseong.csv"
    save_points(points, csv_path, DATA_CLEAN / "03_bus_stops_yuseong.geojson")
    logger.info("버스정류장: %d -> 대전 %d -> 유성구 %d, %s", before, len(daejeon), len(points), encoding)
    return summary_row("버스정류장", before, len(points), missing, duplicates, invalid, csv_path, notes=f"대전 1차 필터 {len(daejeon):,}건 후 공식 경계 공간 필터")


def process_accidents(yuseong: gpd.GeoDataFrame, logger: Any) -> dict[str, Any]:
    """Transform EPSG:5179 accidents and extract 20:00–06:00 records with OR logic."""
    source = DATA_RAW / "05_traffic_accidents" / "05_traffic_accidents.csv"
    frame, encoding = read_csv_safely(source, dtype={"사고번호": "string"})
    before = len(frame)
    duplicates = int(frame.duplicated().sum())
    frame = frame.drop_duplicates().copy()
    frame["발생일시"] = pd.to_datetime(frame["발생일시"], errors="coerce")
    points, missing, invalid = canonicalize_points(frame, "위도", "경도", "EPSG:5179")
    in_boundary = spatial_filter(points, yuseong)
    out_of_boundary = len(points) - len(in_boundary)
    all_csv = DATA_CLEAN / "05_traffic_accidents_all_clean.csv"
    save_points(points, all_csv, DATA_CLEAN / "05_traffic_accidents_all_clean.geojson")
    night_mask = (in_boundary["발생일시"].dt.hour >= 20) | (in_boundary["발생일시"].dt.hour < 6)
    night = in_boundary[night_mask].copy()
    night_csv = DATA_CLEAN / "05_traffic_accidents_night.csv"
    save_points(night, night_csv, DATA_CLEAN / "05_traffic_accidents_night.geojson")
    logger.info("교통사고: 전체 %d, 유성구 경계 %d, 야간 %d, %s", len(points), len(in_boundary), len(night), encoding)
    return summary_row("교통사고", before, len(night), missing, duplicates, invalid + out_of_boundary, night_csv, notes=f"전체 정제 {len(points):,}건; 경계 내부 {len(in_boundary):,}건; 야간 20:00~06:00 OR 조건")


def process_police(yuseong: gpd.GeoDataFrame, logger: Any) -> dict[str, Any]:
    """Correct the inspected swapped WGS84 field meanings for police facilities."""
    source = DATA_RAW / "08_police_stations" / "08_police_stations.csv"
    frame, encoding = read_csv_safely(source)
    before = len(frame)
    duplicates = int(frame.duplicated().sum())
    frame = frame.drop_duplicates().copy()
    source_lat = pd.to_numeric(frame["위도"], errors="coerce")
    source_lon = pd.to_numeric(frame["경도"], errors="coerce")
    swapped = source_lat.median() > 120 and source_lon.median() < 40
    x_column, y_column = ("위도", "경도") if swapped else ("경도", "위도")
    points, missing, invalid = canonicalize_points(frame, x_column, y_column, "EPSG:4326")
    points = spatial_filter(points, yuseong)
    csv_path = DATA_CLEAN / "08_police_stations_clean.csv"
    save_points(points, csv_path, DATA_CLEAN / "08_police_stations_clean.geojson")
    note = "원본 위도/경도 의미 역전 확인 후 위도값(127.x)을 경도, 경도값(36.x)을 위도로 사용" if swapped else "WGS84 위경도 사용"
    logger.info("경찰기관: %d -> %d, %s", before, len(points), encoding)
    return summary_row("경찰기관", before, len(points), missing, duplicates, invalid, csv_path, notes=note)


def main() -> None:
    """Run all available point-data preprocessors independently."""
    logger = configure_logging("points")
    yuseong, _ = load_yuseong_boundaries()
    processors = [process_cctv, process_streetlights, process_bus_stops, process_accidents, process_police]
    rows: list[dict[str, Any]] = []
    for processor in processors:
        try:
            rows.append(processor(yuseong, logger))
        except Exception as exc:
            dataset = processor.__name__.replace("process_", "")
            logger.exception("%s 전처리 실패", dataset)
            rows.append(
                {
                    "dataset": dataset,
                    "status": "failed",
                    "notes": str(exc),
                }
            )
    write_csv(pd.DataFrame(rows), TABLES / "point_preprocessing_summary.csv")


if __name__ == "__main__":
    main()
