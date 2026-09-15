"""Shared utilities for the Yuseong night pedestrian-safety data pipeline."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from zipfile import ZipFile

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = PROJECT_ROOT / "data_raw"
DATA_CLEAN = PROJECT_ROOT / "data_clean"
OUTPUTS = PROJECT_ROOT / "outputs"
TABLES = OUTPUTS / "tables"
MAPS = OUTPUTS / "maps"
LOGS = OUTPUTS / "logs"
BOUNDARY_RAW = DATA_RAW / "boundary"
BOUNDARY_EXTRACTED = BOUNDARY_RAW / "extracted"

ENCODINGS = ("utf-8-sig", "utf-8", "cp949", "euc-kr")

DATASETS: tuple[dict[str, str], ...] = (
    {
        "dataset": "CCTV",
        "relative_path": "01_cctv/01_cctv_national_standard_yuseong.csv",
        "source_url": "https://www.data.go.kr/data/15013094/standard.do",
    },
    {
        "dataset": "가로등",
        "relative_path": "02_streetlights/02_streetlights.csv",
        "source_url": "https://www.data.go.kr/data/15110054/fileData.do",
    },
    {
        "dataset": "버스정류장",
        "relative_path": "03_bus_stops/03_bus_stops.csv",
        "source_url": "https://www.data.go.kr/data/15067528/fileData.do",
    },
    {
        "dataset": "비상벨",
        "relative_path": "04_emergency_bells/04_emergency_bells_by_dong.csv",
        "source_url": "https://www.data.go.kr/data/15111172/fileData.do",
    },
    {
        "dataset": "교통사고",
        "relative_path": "05_traffic_accidents/05_traffic_accidents.csv",
        "source_url": "https://www.data.go.kr/data/15108925/fileData.do",
    },
    {
        "dataset": "유동인구",
        "relative_path": "06_floating_population/06_floating_population_by_dong.zip",
        "source_url": "https://www.data.go.kr/data/15139377/fileData.do",
    },
    {
        "dataset": "성·연령별 주민등록 인구",
        "relative_path": "07_population/07_population_sex_age_by_dong.csv",
        "source_url": "https://www.data.go.kr/data/15108898/fileData.do",
    },
    {
        "dataset": "경찰기관",
        "relative_path": "08_police_stations/08_police_stations.csv",
        "source_url": "https://www.data.go.kr/data/15154551/fileData.do",
    },
)


def ensure_directories() -> None:
    """Create the expected project directories without deleting existing content."""
    directories = [(DATA_RAW / item["relative_path"]).parent for item in DATASETS]
    directories.extend(
        [BOUNDARY_RAW, BOUNDARY_EXTRACTED, DATA_CLEAN, TABLES, MAPS, LOGS, PROJECT_ROOT / "notebooks"]
    )
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def configure_logging(name: str) -> logging.Logger:
    """Configure console and UTF-8 file logging once per script."""
    ensure_directories()
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    file_handler = logging.FileHandler(LOGS / "preprocessing.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def read_csv_safely(path: Path, **kwargs: Any) -> tuple[pd.DataFrame, str]:
    """Read a CSV using a tested Korean-public-data encoding sequence."""
    failures: list[str] = []
    for encoding in ENCODINGS:
        try:
            frame = pd.read_csv(path, encoding=encoding, low_memory=False, **kwargs)
            return frame, encoding
        except UnicodeDecodeError as exc:
            failures.append(f"{encoding}: {exc}")
    raise UnicodeError(f"CSV 인코딩 판별 실패: {path}; {'; '.join(failures)}")


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Write a Korean-friendly UTF-8-with-BOM CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def find_columns(columns: Iterable[object], keywords: Iterable[str]) -> list[str]:
    """Return columns whose normalized names contain any keyword."""
    names = [str(column) for column in columns]
    return [name for name in names if any(keyword.lower() in name.lower() for keyword in keywords)]


def numeric_range(series: pd.Series) -> tuple[float | None, float | None]:
    """Return numeric min/max while ignoring non-numeric and missing values."""
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None, None
    return float(numeric.min()), float(numeric.max())


def safe_extract_boundary_members(archive: Path, destination: Path = BOUNDARY_EXTRACTED) -> list[Path]:
    """Extract only SGIS sigungu/dong SHP members with Zip Slip protection."""
    extracted: list[Path] = []
    destination.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as zipped:
        for info in zipped.infolist():
            pure_path = PurePosixPath(info.filename)
            if pure_path.is_absolute() or ".." in pure_path.parts:
                raise ValueError(f"안전하지 않은 ZIP 내부 경로: {info.filename}")
            filename = pure_path.name
            if not filename or Path(filename).suffix.lower() not in {".shp", ".shx", ".dbf", ".prj", ".cpg"}:
                continue
            normalized = info.filename.replace("\\", "/")
            if "시군구 경계/" in normalized:
                target_dir = destination / "sigungu"
            elif "행정동 경계/" in normalized:
                target_dir = destination / "dong"
            else:
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            target = (target_dir / filename).resolve()
            if destination.resolve() not in target.parents:
                raise ValueError(f"추출 대상이 경계 폴더를 벗어남: {target}")
            with zipped.open(info) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
            extracted.append(target)
    return extracted


def load_yuseong_boundaries() -> tuple[Any, Any]:
    """Load official SGIS 2025 Yuseong sigungu and administrative-dong boundaries."""
    import geopandas as gpd

    archive = BOUNDARY_RAW / "sgis_administrative_boundaries_2025.zip"
    if archive.exists() and not list((BOUNDARY_EXTRACTED / "sigungu").glob("*.shp")):
        safe_extract_boundary_members(archive)

    sigungu_files = list((BOUNDARY_EXTRACTED / "sigungu").glob("*.shp"))
    dong_files = list((BOUNDARY_EXTRACTED / "dong").glob("*.shp"))
    if not sigungu_files or not dong_files:
        raise FileNotFoundError("SGIS 시군구/행정동 SHP가 없습니다.")

    sigungu = gpd.read_file(sigungu_files[0])
    if sigungu.crs is None:
        raise ValueError("SGIS 시군구 경계의 좌표계가 없습니다.")
    name_candidates = [
        str(column)
        for column in sigungu.columns
        if str(column).lower() in {"adm_nm", "sig_kor_nm", "sigungu_nm", "name"}
        or "명" in str(column)
    ]
    if not name_candidates:
        raise KeyError(f"유성구 이름 컬럼을 찾을 수 없습니다: {list(sigungu.columns)}")
    name_column = name_candidates[0]
    yuseong = sigungu[sigungu[name_column].astype("string").str.contains("유성구", na=False)].copy()
    if yuseong.empty:
        raise ValueError(f"SGIS 시군구 경계에서 유성구를 찾지 못했습니다: {name_column}")
    yuseong = yuseong.to_crs(epsg=5179)

    dong = gpd.read_file(dong_files[0]).to_crs(epsg=5179)
    union = yuseong.geometry.union_all()
    inside = dong.geometry.representative_point().within(union)
    yuseong_dong = dong[inside].copy()

    boundary_clean = DATA_CLEAN / "boundary"
    boundary_clean.mkdir(parents=True, exist_ok=True)
    yuseong.to_file(boundary_clean / "yuseong_sigungu_5179.geojson", driver="GeoJSON")
    yuseong.to_crs(epsg=4326).to_file(
        boundary_clean / "yuseong_sigungu_4326.geojson", driver="GeoJSON"
    )
    yuseong_dong.to_crs(epsg=4326).to_file(
        boundary_clean / "yuseong_admdong_4326.geojson", driver="GeoJSON"
    )
    return yuseong, yuseong_dong


def save_point_outputs(
    frame: pd.DataFrame,
    *,
    x_column: str,
    y_column: str,
    source_crs: str,
    csv_path: Path,
    geojson_path: Path,
) -> Any:
    """Create canonical EPSG:5179/WGS84 columns and save CSV plus GeoJSON."""
    import geopandas as gpd

    cleaned = frame.copy()
    cleaned[x_column] = pd.to_numeric(cleaned[x_column], errors="coerce")
    cleaned[y_column] = pd.to_numeric(cleaned[y_column], errors="coerce")
    cleaned = cleaned.dropna(subset=[x_column, y_column]).copy()
    geometry = gpd.points_from_xy(cleaned[x_column], cleaned[y_column])
    points = gpd.GeoDataFrame(cleaned, geometry=geometry, crs=source_crs)
    points_5179 = points.to_crs(epsg=5179)
    points_wgs84 = points.to_crs(epsg=4326)
    cleaned["x_5179"] = points_5179.geometry.x.to_numpy()
    cleaned["y_5179"] = points_5179.geometry.y.to_numpy()
    cleaned["longitude"] = points_wgs84.geometry.x.to_numpy()
    cleaned["latitude"] = points_wgs84.geometry.y.to_numpy()
    valid = cleaned["longitude"].between(124, 132) & cleaned["latitude"].between(33, 39)
    cleaned = cleaned.loc[valid].copy()
    write_csv(cleaned, csv_path)
    output = gpd.GeoDataFrame(
        cleaned,
        geometry=gpd.points_from_xy(cleaned["longitude"], cleaned["latitude"]),
        crs="EPSG:4326",
    )
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_file(geojson_path, driver="GeoJSON")
    return output


def configure_korean_font() -> str | None:
    """Configure a common Windows Korean font when available."""
    try:
        import matplotlib
        from matplotlib import font_manager

        candidates = [
            Path("C:/Windows/Fonts/malgun.ttf"),
            Path("C:/Windows/Fonts/NanumGothic.ttf"),
        ]
        for path in candidates:
            if path.exists():
                font_manager.fontManager.addfont(str(path))
                family = font_manager.FontProperties(fname=str(path)).get_name()
                matplotlib.rcParams["font.family"] = family
                matplotlib.rcParams["axes.unicode_minus"] = False
                return family
    except Exception:
        return None
    return None
