"""Inspect raw files before dataset-specific preprocessing."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

from common import (
    DATASETS,
    DATA_RAW,
    TABLES,
    configure_logging,
    find_columns,
    numeric_range,
    read_csv_safely,
    write_csv,
)


def inspect_csv(dataset: str, path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Return one file inventory row plus one row per source column."""
    frame, encoding = read_csv_safely(path)
    coordinate_columns = find_columns(frame.columns, ("위도", "경도", "x좌표", "y좌표", "좌표"))
    address_columns = find_columns(frame.columns, ("주소", "설치위치"))
    admin_columns = find_columns(frame.columns, ("행정동", "법정동", "시군구", "도시명"))
    date_columns = find_columns(frame.columns, ("기준", "일시", "수집일", "년도", "년월"))

    ranges: list[str] = []
    for column in coordinate_columns:
        minimum, maximum = numeric_range(frame[column])
        ranges.append(f"{column}={minimum}..{maximum}")

    inventory = {
        "dataset": dataset,
        "file_name": path.name,
        "relative_path": str(path.relative_to(DATA_RAW.parent)),
        "encoding": encoding,
        "rows": len(frame),
        "columns": len(frame.columns),
        "duplicate_rows": int(frame.duplicated().sum()),
        "total_missing_cells": int(frame.isna().sum().sum()),
        "coordinate_columns": " | ".join(coordinate_columns),
        "coordinate_ranges": " | ".join(ranges),
        "address_columns": " | ".join(address_columns),
        "admin_columns": " | ".join(admin_columns),
        "date_columns": " | ".join(date_columns),
        "status": "inspected",
        "notes": "",
    }
    if dataset == "경찰기관":
        lat_min, lat_max = numeric_range(frame["위도"])
        lon_min, lon_max = numeric_range(frame["경도"])
        if lat_min and lon_min and lat_min > 120 and lon_max < 40:
            inventory["status"] = "needs_review"
            inventory["notes"] = "원본 위도=경도값(127.x), 경도=위도값(36.x)으로 의미가 뒤바뀜"

    column_rows = [
        {
            "dataset": dataset,
            "file_name": path.name,
            "column_order": index + 1,
            "column_name": str(column),
            "dtype": str(frame[column].dtype),
            "missing_count": int(frame[column].isna().sum()),
            "unique_count": int(frame[column].nunique(dropna=True)),
            "sample_values": " | ".join(frame[column].dropna().astype(str).head(3).tolist()),
        }
        for index, column in enumerate(frame.columns)
    ]
    return inventory, column_rows


def inspect_floating_zip(dataset: str, path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Inspect and combine CSV members in the floating-population ZIP without extraction."""
    frames: list[pd.DataFrame] = []
    encodings: list[str] = []
    with ZipFile(path) as zipped:
        members = [info for info in zipped.infolist() if info.filename.lower().endswith(".csv")]
        for info in members:
            payload = zipped.read(info)
            for encoding in ("utf-8-sig", "cp949", "utf-8"):
                try:
                    frames.append(pd.read_csv(BytesIO(payload), encoding=encoding))
                    encodings.append(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise UnicodeDecodeError("unknown", b"", 0, 1, f"인코딩 확인 실패: {info.filename}")
    if not frames:
        raise ValueError("유동인구 ZIP 내부 CSV가 없습니다.")
    frame = pd.concat(frames, ignore_index=True, sort=False)
    inventory = {
        "dataset": dataset,
        "file_name": path.name,
        "relative_path": str(path.relative_to(DATA_RAW.parent)),
        "encoding": f"{encodings[0]} ({len(frames)} CSV)",
        "rows": len(frame),
        "columns": len(frame.columns),
        "duplicate_rows": int(frame.duplicated().sum()),
        "total_missing_cells": int(frame.isna().sum().sum()),
        "coordinate_columns": "",
        "coordinate_ranges": "",
        "address_columns": "",
        "admin_columns": "행정동" if "행정동" in frame.columns else "",
        "date_columns": "월" if "월" in frame.columns else "",
        "status": "inspected",
        "notes": f"ZIP 내부 월별 CSV {len(frames)}개 통합 점검",
    }
    column_rows = [
        {
            "dataset": dataset,
            "file_name": path.name,
            "column_order": index + 1,
            "column_name": str(column),
            "dtype": str(frame[column].dtype),
            "missing_count": int(frame[column].isna().sum()),
            "unique_count": int(frame[column].nunique(dropna=True)),
            "sample_values": " | ".join(frame[column].dropna().astype(str).head(3).tolist()),
        }
        for index, column in enumerate(frame.columns)
    ]
    return inventory, column_rows


def main() -> None:
    """Inspect every expected raw dataset and write auditable CSV tables."""
    logger = configure_logging("inspect")
    inventories: list[dict[str, object]] = []
    columns: list[dict[str, object]] = []
    preprocessing: list[dict[str, object]] = []

    for item in DATASETS:
        path = DATA_RAW / item["relative_path"]
        if path.suffix.lower() == ".zip" and path.exists() and item["dataset"] == "유동인구":
            inventory, column_rows = inspect_floating_zip(item["dataset"], path)
            inventories.append(inventory)
            columns.extend(column_rows)
            preprocessing.append(
                {
                    "dataset": item["dataset"],
                    "original_rows": inventory["rows"],
                    "filtered_rows": None,
                    "missing_coordinate_rows": None,
                    "duplicate_rows_removed": None,
                    "invalid_coordinate_rows": None,
                    "output_file": "",
                    "status": inventory["status"],
                    "notes": inventory["notes"],
                }
            )
            logger.info("%s: ZIP 내부 %s행 × %s열, %s", item["dataset"], inventory["rows"], inventory["columns"], inventory["encoding"])
            continue
        if path.suffix.lower() != ".csv" or not path.exists():
            note = "원본 파일 없음" if not path.exists() else "ZIP은 전용 전처리 단계에서 검사"
            inventories.append(
                {
                    "dataset": item["dataset"],
                    "file_name": path.name,
                    "relative_path": str(path.relative_to(DATA_RAW.parent)),
                    "status": "missing" if not path.exists() else "pending_zip_inspection",
                    "notes": note,
                }
            )
            preprocessing.append(
                {
                    "dataset": item["dataset"],
                    "original_rows": None,
                    "filtered_rows": None,
                    "missing_coordinate_rows": None,
                    "duplicate_rows_removed": None,
                    "invalid_coordinate_rows": None,
                    "output_file": "",
                    "status": "missing" if not path.exists() else "pending",
                    "notes": note,
                }
            )
            logger.warning("%s: %s", item["dataset"], note)
            continue
        inventory, column_rows = inspect_csv(item["dataset"], path)
        inventories.append(inventory)
        columns.extend(column_rows)
        preprocessing.append(
            {
                "dataset": item["dataset"],
                "original_rows": inventory["rows"],
                "filtered_rows": None,
                "missing_coordinate_rows": None,
                "duplicate_rows_removed": None,
                "invalid_coordinate_rows": None,
                "output_file": "",
                "status": inventory["status"],
                "notes": inventory["notes"],
            }
        )
        logger.info("%s: %s행 × %s열, %s", item["dataset"], inventory["rows"], inventory["columns"], inventory["encoding"])

    write_csv(pd.DataFrame(inventories), TABLES / "raw_data_inventory.csv")
    write_csv(pd.DataFrame(columns), TABLES / "raw_data_columns.csv")
    write_csv(pd.DataFrame(preprocessing), TABLES / "preprocessing_summary.csv")


if __name__ == "__main__":
    main()
