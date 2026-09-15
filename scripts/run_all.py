"""Run all pipeline stages while continuing past dataset-specific failures."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

from common import configure_logging


SCRIPTS = (
    "01_download_data.py",
    "02_inspect_raw_data.py",
    "03_preprocess_point_data.py",
    "04_preprocess_population_data.py",
    "05_create_static_maps.py",
    "06_create_interactive_map.py",
    "07_create_interim_summary.py",
)


def main() -> None:
    """Execute every stage in order and log failures without aborting the run."""
    logger = configure_logging("run_all")
    scripts_dir = Path(__file__).resolve().parent
    failures: list[str] = []
    for script_name in SCRIPTS:
        logger.info("시작: %s", script_name)
        result = subprocess.run([sys.executable, str(scripts_dir / script_name)], check=False)
        if result.returncode:
            failures.append(script_name)
            logger.error("실패(%d): %s", result.returncode, script_name)
        else:
            logger.info("완료: %s", script_name)
    if failures:
        logger.warning("일부 단계 실패: %s", ", ".join(failures))
    else:
        logger.info("전체 단계 완료")


if __name__ == "__main__":
    main()
