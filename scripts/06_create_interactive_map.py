"""Create a Folium layer-control map from available verified datasets."""

from __future__ import annotations

import folium
import geopandas as gpd
import pandas as pd
from folium.plugins import FastMarkerCluster, HeatMap, MarkerCluster

from common import DATA_CLEAN, MAPS, configure_logging, load_yuseong_boundaries


def load_wgs84(filename: str) -> gpd.GeoDataFrame | None:
    """Load one optional GeoJSON in EPSG:4326."""
    path = DATA_CLEAN / filename
    return gpd.read_file(path).to_crs(epsg=4326) if path.exists() else None


def main() -> None:
    """Build a switchable interim-status web map without personal information."""
    logger = configure_logging("interactive_map")
    boundary, dong = load_yuseong_boundaries()
    boundary_wgs = boundary.to_crs(epsg=4326)
    dong_wgs = dong.to_crs(epsg=4326)
    center = boundary_wgs.geometry.union_all().centroid
    web_map = folium.Map(location=[center.y, center.x], zoom_start=12, tiles="CartoDB positron", control_scale=True)
    folium.GeoJson(boundary_wgs, name="유성구 경계", style_function=lambda _: {"color": "#334155", "weight": 2, "fillOpacity": 0.03}).add_to(web_map)

    floating_path = DATA_CLEAN / "06_floating_population_by_dong_summary.csv"
    if floating_path.exists():
        floating = pd.read_csv(floating_path, encoding="utf-8-sig")
        name_column = "ADM_NM" if "ADM_NM" in dong_wgs.columns else next(column for column in dong_wgs.columns if "NM" in str(column).upper())
        folium.Choropleth(
            geo_data=dong_wgs.__geo_interface__,
            data=floating,
            columns=["행정동", "daily_average_2023"],
            key_on=f"feature.properties.{name_column}",
            name="2023년 일평균 유동인구",
            fill_color="YlOrRd",
            fill_opacity=0.68,
            line_opacity=0.65,
            legend_name="2023년 일평균 유동인구 (명)",
            show=False,
        ).add_to(web_map)
        floating_layer = dong_wgs.merge(floating, left_on=name_column, right_on="행정동", how="left")
        folium.GeoJson(
            floating_layer,
            name="유동인구 행정동 정보",
            style_function=lambda _: {"color": "#64748B", "weight": 0.6, "fillOpacity": 0},
            tooltip=folium.GeoJsonTooltip(
                fields=[name_column, "daily_average_2023", "monthly_min", "monthly_max"],
                aliases=["행정동", "2023 일평균", "월 최솟값", "월 최댓값"],
                localize=True,
                sticky=False,
            ),
            show=False,
        ).add_to(web_map)

    cctv = load_wgs84("01_cctv_yuseong_standard.geojson")
    if cctv is not None:
        group = folium.FeatureGroup(name=f"CCTV 설치지점 ({len(cctv):,})", show=True)
        cluster = MarkerCluster().add_to(group)
        for _, row in cctv.iterrows():
            camera_count = row.get("카메라대수", "")
            purpose = row.get("설치목적구분", "")
            folium.Marker(
                [row.geometry.y, row.geometry.x],
                tooltip=f"CCTV {camera_count}대 · {purpose}",
                icon=folium.Icon(color="purple", icon="video-camera", prefix="fa"),
            ).add_to(cluster)
        group.add_to(web_map)

    streetlights = load_wgs84("02_streetlights_yuseong.geojson")
    if streetlights is not None:
        group = folium.FeatureGroup(name=f"가로등 ({len(streetlights):,})", show=False)
        FastMarkerCluster(streetlights[["latitude", "longitude"]].values.tolist()).add_to(group)
        group.add_to(web_map)

    buses = load_wgs84("03_bus_stops_yuseong.geojson")
    if buses is not None:
        group = folium.FeatureGroup(name=f"버스정류장 ({len(buses):,})", show=False)
        cluster = MarkerCluster().add_to(group)
        for _, row in buses.iterrows():
            folium.Marker([row.geometry.y, row.geometry.x], tooltip=str(row.get("정류장명", "버스정류장")), icon=folium.Icon(color="green", icon="bus", prefix="fa")).add_to(cluster)
        group.add_to(web_map)

    accidents = load_wgs84("05_traffic_accidents_night.geojson")
    if accidents is not None:
        group = folium.FeatureGroup(name=f"야간 교통사고 ({len(accidents):,})", show=True)
        HeatMap([[geometry.y, geometry.x] for geometry in accidents.geometry], radius=12, blur=14).add_to(group)
        group.add_to(web_map)

    police = load_wgs84("08_police_stations_clean.geojson")
    if police is not None:
        group = folium.FeatureGroup(name=f"경찰기관 ({len(police):,})", show=True)
        for _, row in police.iterrows():
            folium.Marker([row.geometry.y, row.geometry.x], tooltip=str(row.get("기관명", "경찰기관")), popup=f"{row.get('기관명', '')}<br>{row.get('행정동명', '')}", icon=folium.Icon(color="red", icon="shield", prefix="fa")).add_to(group)
        group.add_to(web_map)

    note = "CCTV는 행정안전부 전국CCTV표준데이터의 WGS84 좌표를 사용했습니다. 본 지도는 현황 중첩이며 취약지역 판정 결과가 아닙니다."
    folium.map.Marker([center.y, center.x], icon=folium.DivIcon(html=f'<div style="width:380px;background:white;border:1px solid #cbd5e1;padding:8px;font-size:12px;">{note}</div>')).add_to(web_map)
    folium.LayerControl(collapsed=False).add_to(web_map)
    output = MAPS / "yuseong_night_safety_map.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    web_map.save(output)
    logger.info("대화형 지도 저장: %s", output)


if __name__ == "__main__":
    main()
