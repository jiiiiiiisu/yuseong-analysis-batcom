"""Preprocess emergency-bell, floating-population, and demographic datasets."""

from __future__ import annotations

import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

import pandas as pd

from common import DATA_CLEAN, DATA_RAW, TABLES, configure_logging, find_columns, read_csv_safely, write_csv


def process_emergency_bells(logger: Any) -> dict[str, Any]:
    """Aggregate law-dong rows to administrative dong and calculate per-1,000 rate."""
    source = DATA_RAW / "04_emergency_bells" / "04_emergency_bells_by_dong.csv"
    frame, encoding = read_csv_safely(source)
    grouped = (
        frame.groupby(["행정동코드", "행정동이름"], dropna=False, as_index=False)
        .agg(
            emergency_bell_count=("비상벨수", "sum"),
            population=("인구수", "sum"),
            legal_dong_count=("법정동코드", "nunique"),
        )
        .sort_values("행정동이름")
    )
    grouped["emergency_bells_per_1000"] = grouped["emergency_bell_count"].div(grouped["population"]).mul(1000)
    output = DATA_CLEAN / "04_emergency_bells_by_dong_clean.csv"
    write_csv(grouped, output)
    logger.info("비상벨: %d 법정동 행 -> %d 행정동, %s", len(frame), len(grouped), encoding)
    return {"dataset": "비상벨", "original_rows": len(frame), "filtered_rows": len(grouped), "output_file": str(output.relative_to(DATA_CLEAN.parent)), "status": "completed", "notes": "행정동별 합계 및 인구 1,000명당 비상벨 수"}


def parse_reference_month(series: pd.Series) -> pd.Series:
    """Parse strings such as Jan-22 without depending on the OS locale."""
    month_map = {name: index for index, name in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), start=1)}

    def convert(value: object) -> pd.Timestamp | pd.NaT:
        text = str(value).strip()
        match = re.fullmatch(r"([A-Za-z]{3})-(\d{2,4})", text)
        if match and match.group(1).title() in month_map:
            year_text = match.group(2)
            year = int(year_text) + (2000 if len(year_text) == 2 else 0)
            return pd.Timestamp(year=year, month=month_map[match.group(1).title()], day=1)
        return pd.to_datetime(text, errors="coerce")

    return series.map(convert)


def process_population(logger: Any) -> dict[str, Any]:
    """Calculate latest-month total, female, and age-65-plus population by dong."""
    source = DATA_RAW / "07_population" / "07_population_sex_age_by_dong.csv"
    frame, encoding = read_csv_safely(source, dtype={"행정동코드": "string"})
    original = len(frame)
    frame = frame[frame["시군구이름"].astype("string").str.contains("유성구", na=False)].copy()
    frame["reference_month"] = parse_reference_month(frame["기준년월"])
    latest = frame["reference_month"].max()
    if pd.notna(latest):
        frame = frame[frame["reference_month"] == latest].copy()
    frame = frame.dropna(subset=["행정동이름"]).copy()
    frame["인구수"] = pd.to_numeric(frame["인구수"], errors="coerce").fillna(0)
    frame["연령"] = pd.to_numeric(frame["연령"], errors="coerce")
    base = frame.groupby(["행정동코드", "행정동이름"], as_index=False)["인구수"].sum().rename(columns={"인구수": "total_population"})
    female = frame[frame["성별"].astype("string").str.contains("여", na=False)].groupby(["행정동코드", "행정동이름"], as_index=False)["인구수"].sum().rename(columns={"인구수": "female_population"})
    elderly = frame[frame["연령"] >= 65].groupby(["행정동코드", "행정동이름"], as_index=False)["인구수"].sum().rename(columns={"인구수": "elderly_population"})
    summary = base.merge(female, on=["행정동코드", "행정동이름"], how="left").merge(elderly, on=["행정동코드", "행정동이름"], how="left")
    summary[["female_population", "elderly_population"]] = summary[["female_population", "elderly_population"]].fillna(0)
    summary["female_ratio"] = summary["female_population"].div(summary["total_population"])
    summary["elderly_ratio"] = summary["elderly_population"].div(summary["total_population"])
    summary["reference_month"] = latest.strftime("%Y-%m") if pd.notna(latest) else ""
    summary = summary.sort_values("행정동이름")
    output = DATA_CLEAN / "07_population_by_dong_summary.csv"
    write_csv(summary, output)
    logger.info("인구: %d -> 최신월 %s, %d 행정동, %s", original, latest, len(summary), encoding)
    return {"dataset": "성·연령별 주민등록 인구", "original_rows": original, "filtered_rows": len(summary), "output_file": str(output.relative_to(DATA_CLEAN.parent)), "status": "completed", "notes": f"최신 기준월 {latest:%Y-%m}; 여성 및 65세 이상 지표" if pd.notna(latest) else "기준월 파싱 필요"}


def safe_extract_floating_csvs(archive: Path, destination: Path) -> list[Path]:
    """Extract only CSV members from a floating-population ZIP with path validation."""
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    with ZipFile(archive) as zipped:
        for info in zipped.infolist():
            pure = PurePosixPath(info.filename)
            if pure.is_absolute() or ".." in pure.parts:
                raise ValueError(f"안전하지 않은 ZIP 내부 경로: {info.filename}")
            if not pure.name.lower().endswith(".csv"):
                continue
            target = (destination / pure.name).resolve()
            if destination.resolve() not in target.parents:
                raise ValueError(f"추출 대상이 폴더를 벗어남: {target}")
            with zipped.open(info) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
            extracted.append(target)
    return extracted


def process_floating_population(logger: Any) -> dict[str, Any]:
    """Combine 2023 monthly files and summarize daily-average floating population."""
    archive = DATA_RAW / "06_floating_population" / "06_floating_population_by_dong.zip"
    if not archive.exists():
        logger.warning("유동인구 ZIP 없음: %s", archive)
        return {"dataset": "유동인구", "original_rows": None, "filtered_rows": None, "output_file": "", "status": "missing", "notes": "포털에서 수동 다운로드 필요"}
    monthly_dir = DATA_RAW / "06_floating_population_monthly"
    files = safe_extract_floating_csvs(archive, monthly_dir)
    frames: list[pd.DataFrame] = []
    for file in files:
        frame, _ = read_csv_safely(file)
        frame["source_file"] = file.name
        frames.append(frame)
    if not frames:
        return {"dataset": "유동인구", "status": "needs_review", "notes": "ZIP 내부 CSV 없음"}
    combined = pd.concat(frames, ignore_index=True, sort=False)
    output_combined = DATA_CLEAN / "06_floating_population_monthly_combined.csv"
    write_csv(combined, output_combined)
    dong_columns = find_columns(combined.columns, ("행정동",))
    value_columns = find_columns(combined.columns, ("일평균", "일평군", "유동인구"))
    if not dong_columns or not value_columns:
        return {"dataset": "유동인구", "original_rows": len(combined), "filtered_rows": None, "output_file": str(output_combined.relative_to(DATA_CLEAN.parent)), "status": "needs_review", "notes": f"실제 컬럼 확인 필요: {list(combined.columns)}"}
    dong_column, value_column = dong_columns[0], value_columns[-1]
    month_columns = find_columns(combined.columns, ("월", "기준년월"))
    month_column = month_columns[0] if month_columns else None
    combined[value_column] = pd.to_numeric(combined[value_column], errors="coerce")
    if month_column:
        combined[month_column] = combined[month_column].astype("string").str.strip()
    aggregations: dict[str, tuple[str, str]] = {
        "daily_average_2023": (value_column, "mean"),
        "monthly_min": (value_column, "min"),
        "monthly_max": (value_column, "max"),
    }
    if month_column:
        aggregations["months_observed"] = (month_column, "nunique")
    summary = combined.groupby(dong_column, as_index=False).agg(**aggregations)
    if "months_observed" not in summary:
        summary["months_observed"] = len(files)
    summary["reference_period"] = "2023-01~2023-12"
    summary = summary.sort_values(dong_column)
    output_summary = DATA_CLEAN / "06_floating_population_by_dong_summary.csv"
    write_csv(summary, output_summary)
    write_csv(summary, TABLES / "floating_population_by_dong_summary.csv")
    complete_months = bool((summary["months_observed"] == 12).all())
    complete_dongs = len(summary) == 13
    status = "completed" if complete_months and complete_dongs else "needs_review"
    logger.info("유동인구: %d개 CSV, %d행, %d행정동", len(files), len(combined), len(summary))
    return {
        "dataset": "유동인구",
        "original_rows": len(combined),
        "filtered_rows": len(summary),
        "output_file": str(output_summary.relative_to(DATA_CLEAN.parent)),
        "status": status,
        "notes": "2023년 12개월·13개 행정동 일평균 자료 통합; 시간대 자료 없음",
    }


def main() -> None:
    """Run each population-like dataset independently and record failures."""
    logger = configure_logging("population")
    rows: list[dict[str, Any]] = []
    for processor in (process_emergency_bells, process_floating_population, process_population):
        try:
            rows.append(processor(logger))
        except Exception as exc:
            logger.exception("%s 실패", processor.__name__)
            rows.append({"dataset": processor.__name__, "status": "failed", "notes": str(exc)})
    write_csv(pd.DataFrame(rows), TABLES / "population_preprocessing_summary.csv")


if __name__ == "__main__":
    main()
