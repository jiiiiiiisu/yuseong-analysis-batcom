"""Create interim report tables and reconcile displayed feature counts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from common import DATA_CLEAN, DATA_RAW, TABLES, configure_logging, read_csv_safely, write_csv


def row_count(path: Path) -> int | None:
    """Count CSV rows when an output exists."""
    if not path.exists():
        return None
    return len(pd.read_csv(path, encoding="utf-8-sig", low_memory=False))


def main() -> None:
    """Build presentation tables from actual clean outputs without fabricated values."""
    logger = configure_logging("summary")
    point_summary_path = TABLES / "point_preprocessing_summary.csv"
    population_summary_path = TABLES / "population_preprocessing_summary.csv"
    point_summary = pd.read_csv(point_summary_path, encoding="utf-8-sig") if point_summary_path.exists() else pd.DataFrame()
    population_summary = pd.read_csv(population_summary_path, encoding="utf-8-sig") if population_summary_path.exists() else pd.DataFrame()
    combined_summary = pd.concat([point_summary, population_summary], ignore_index=True, sort=False)
    write_csv(combined_summary, TABLES / "preprocessing_summary.csv")

    cctv_raw, _ = read_csv_safely(
        DATA_RAW / "01_cctv" / "01_cctv_national_standard_yuseong.csv",
        dtype={"관리번호": "string"},
    )

    source_rows = {
        "CCTV": len(cctv_raw),
        "가로등": 43082,
        "버스정류장": 227065,
        "비상벨": 61,
        "교통사고": 9579,
        "유동인구": row_count(DATA_CLEAN / "06_floating_population_monthly_combined.csv"),
        "성·연령별 주민등록 인구": 41182,
        "경찰기관": 10,
    }
    clean_counts = {
        "CCTV": row_count(DATA_CLEAN / "01_cctv_yuseong_standard.csv"),
        "가로등": row_count(DATA_CLEAN / "02_streetlights_yuseong.csv"),
        "버스정류장": row_count(DATA_CLEAN / "03_bus_stops_yuseong.csv"),
        "비상벨": row_count(DATA_CLEAN / "04_emergency_bells_by_dong_clean.csv"),
        "교통사고": row_count(DATA_CLEAN / "05_traffic_accidents_night.csv"),
        "유동인구": row_count(DATA_CLEAN / "06_floating_population_by_dong_summary.csv"),
        "성·연령별 주민등록 인구": row_count(DATA_CLEAN / "07_population_by_dong_summary.csv"),
        "경찰기관": row_count(DATA_CLEAN / "08_police_stations_clean.csv"),
    }
    coordinate_datasets = {"CCTV", "가로등", "버스정류장", "교통사고", "경찰기관"}
    interim_rows: list[dict[str, Any]] = []
    for dataset, original_rows in source_rows.items():
        status_row = combined_summary[combined_summary.get("dataset", pd.Series(dtype=str)) == dataset]
        status = status_row.iloc[-1]["status"] if not status_row.empty and "status" in status_row else "missing"
        notes = status_row.iloc[-1].get("notes", "") if not status_row.empty else ""
        count = clean_counts[dataset]
        interim_rows.append(
            {
                "데이터명": dataset,
                "원본 행 수": original_rows,
                "유성구 필터링 후 행 수": count,
                "좌표 사용 가능 행 수": count if dataset in coordinate_datasets and status == "completed" else None,
                "지도 표시 행 수": count if dataset in {"CCTV", "가로등", "버스정류장", "교통사고", "유동인구", "경찰기관"} else None,
                "전처리 상태": status,
                "비고": notes,
            }
        )
    write_csv(pd.DataFrame(interim_rows), TABLES / "interim_data_summary.csv")

    key_rows: list[dict[str, Any]] = []

    def add(statistic: str, value: Any, unit: str, reason: str = "") -> None:
        key_rows.append({"통계항목": statistic, "값": value, "단위": unit, "미산출 사유 또는 비고": reason})

    cctv_clean = pd.read_csv(DATA_CLEAN / "01_cctv_yuseong_standard.csv", encoding="utf-8-sig")
    cctv_camera_total = pd.to_numeric(cctv_clean["카메라대수"], errors="coerce").sum()
    add("CCTV 설치지점 개수", clean_counts["CCTV"], "개소", f"전국표준 유성구 {len(cctv_raw):,}행 중 공식 경계 내부")
    add("CCTV 카메라 대수 합계", cctv_camera_total, "대", "설치지점별 카메라대수 합계")
    add("유성구 가로등 개수", clean_counts["가로등"], "개소")
    add("유성구 버스정류장 개수", clean_counts["버스정류장"], "개소")
    accident_all = row_count(DATA_CLEAN / "05_traffic_accidents_all_clean.csv")
    accident_night = clean_counts["교통사고"]
    add("전체 교통사고 개수", accident_all, "건")
    add("야간 교통사고 개수", accident_night, "건", "공식 유성구 경계 내부, 20:00~06:00")
    add("야간 사고 비율", accident_night / accident_all if accident_all else None, "비율")
    add("경찰기관 개수", clean_counts["경찰기관"], "개소")
    floating_path = DATA_CLEAN / "06_floating_population_by_dong_summary.csv"
    if floating_path.exists():
        floating = pd.read_csv(floating_path, encoding="utf-8-sig")
        add("행정동별 2023년 일평균 유동인구 최소", floating["daily_average_2023"].min(), "명", "12개월 월별 일평균의 평균")
        add("행정동별 2023년 일평균 유동인구 최대", floating["daily_average_2023"].max(), "명", "12개월 월별 일평균의 평균")
        add("행정동별 2023년 일평균 유동인구 평균", floating["daily_average_2023"].mean(), "명", "13개 행정동 평균")
    else:
        add("행정동별 유동인구 평균", None, "명", "원본 ZIP 미확보")

    population_path = DATA_CLEAN / "07_population_by_dong_summary.csv"
    if population_path.exists():
        population = pd.read_csv(population_path, encoding="utf-8-sig")
        for column, label in (("female_ratio", "행정동별 여성인구 비율"), ("elderly_ratio", "행정동별 고령인구 비율")):
            add(f"{label} 최소", population[column].min(), "비율")
            add(f"{label} 최대", population[column].max(), "비율")
            add(f"{label} 평균", population[column].mean(), "비율")
    write_csv(pd.DataFrame(key_rows), TABLES / "key_statistics.csv")
    logger.info("중간보고 요약표 및 핵심통계 생성")


if __name__ == "__main__":
    main()
