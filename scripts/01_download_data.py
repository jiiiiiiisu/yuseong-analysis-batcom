"""Check downloaded source files and safely extract official SGIS boundaries."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from common import (
    BOUNDARY_RAW,
    DATASETS,
    DATA_RAW,
    TABLES,
    configure_logging,
    ensure_directories,
    safe_extract_boundary_members,
    write_csv,
)


def main() -> None:
    """Record data availability without modifying any downloaded originals."""
    logger = configure_logging("download")
    ensure_directories()
    rows: list[dict[str, object]] = []
    for item in DATASETS:
        path = DATA_RAW / item["relative_path"]
        status = "downloaded" if path.exists() else "missing"
        notes = ""
        if item["dataset"] == "유동인구" and not path.exists():
            notes = "포털 다운로드 버튼이 파일 전송을 시작하지 않음; 사용자가 수동 다운로드 필요"
        rows.append(
            {
                "dataset": item["dataset"],
                "expected_file": str(path.relative_to(DATA_RAW.parent)),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
                "status": status,
                "source_url": item["source_url"],
                "notes": notes,
            }
        )
        logger.info("%s: %s", item["dataset"], status)

    archive = BOUNDARY_RAW / "sgis_administrative_boundaries_2025.zip"
    if archive.exists():
        extracted = safe_extract_boundary_members(archive)
        logger.info("SGIS 경계 구성 파일 %d개 안전 추출", len(extracted))
    else:
        logger.warning("SGIS 공식 경계 ZIP이 없습니다: %s", archive)

    write_csv(pd.DataFrame(rows), TABLES / "download_status.csv")


if __name__ == "__main__":
    main()
