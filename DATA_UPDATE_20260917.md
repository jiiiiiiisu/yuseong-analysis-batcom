# 신규 데이터 정제 기록 (2026-09-17)

## 결론

기존 정제본은 덮어쓰지 않았다. 중복이 아닌 공공데이터 4종과 유성구청 제공 50m 야간 유동인구의 공개용 집계본을 추가했다.

유성구청 제공 원본은 직접 개인정보 필드가 없지만, 50m 격자·일자·시간대 조합이 세밀하므로 GitHub 공개 대상에서 제외한다. 공개용 파일은 500m 격자와 월 단위로 집계했고, 한 달에 기여한 50m 셀이 4개 미만인 500m 격자 결과를 제외했다.

## 추가한 정제 파일

| 파일 | 행 수 | 내용 |
|---|---:|---|
| `data_clean/10_security_lights_population_by_legal_dong.csv` | 61 | 법정동별 보안등 수·인구·비율, 인구 1천 명당 보안등 재계산 |
| `data_clean/11_floating_population_legal_dong_2020_2022.csv` | 9,512 | 2020-01~2022-12 법정동·시간대별 일평균 유동인구 통합 |
| `data_clean/12_village_bus_stop_routes_clean.csv` | 298 | 마을버스 노선-정류장 단위 정제본 |
| `data_clean/12b_village_bus_stops_unique.csv` | 264 | 정류장 관리번호 기준 중복 제거, 노선·방향 목록 통합 |
| `data_clean/13_emergency_bells_point_clean.csv` | 145 | 비상벨 위치 단위 정제본, 표시위치 보완 및 좌표 유효성 검사 |
| `data_clean/14_night_population_500m_monthly_202508_202607.csv` | 8,262 | 500m 격자별 2025-08~2026-07 월평균 야간 인구 |
| `data_clean/14b_night_population_500m_period_average.csv` | 712 | 500m 격자별 전체 기간 가중평균 야간 인구 |

CSV는 Excel에서 한글이 깨지지 않도록 UTF-8 BOM으로 저장했다.

## 중복 또는 제외한 자료

- CCTV 설치현황: 기존 `01_cctv_clean.csv`와 같은 672건 자료이므로 재정제하지 않음.
- 경찰서 현황: 새로 받은 파일과 기존 `data_raw/08_police_stations.csv`의 SHA-256이 동일함. 실제 파일은 10행이므로 기존 `08_police_stations_clean.csv` 유지.
- 유성구청 50m 원본 Parquet와 GPKG: 공개 저장소에 복사하지 않음. 원본은 로컬 다운로드 폴더에만 유지.

## 원자료에서 확인한 주의사항

- `동별 인구 대비 보안등 현황`은 행정동 합계가 아니라 법정동별 행이 포함된 자료다. 제공 기준년도는 2021년이다.
- `법정동별 일평균 유동인구`는 2026년 자료가 아니라 2020~2022년 자료다. 2022년 2월 5행은 법정동코드와 법정동명이 비어 있어 `원자료_법정동누락=True`, `미상(원자료 누락)`으로 보존했다.
- `버스 정류장정보` 원본은 61행이 아니라 299행이다. 완전 중복 1행을 제거해 노선-정류장 정제본은 298행이며, 고유 정류장은 264곳이다.
- `경찰서 현황` 원본의 `위도`, `경도` 열 이름은 실제 값의 방향과 반대로 보이지만 기존 정제본에서 WGS84 경도·위도 열을 별도로 정리해 두었다.
- 50m 야간 유동인구 월평균은 해당 월의 모든 야간 시간 슬롯(22~06시, 하루 9개)을 분모로 사용했다. 원본에 없는 셀-시간 조합은 0으로 간주한다.
- `source_coverage_pct`는 원본에 실제로 존재한 셀-시간 행 비율이다. 값이 낮은 곳은 해석 시 주의한다.

## 출처

- CCTV: https://www.data.go.kr/data/15108945/fileData.do
- 동별 인구 대비 보안등: https://www.data.go.kr/data/15111161/fileData.do
- 법정동별 일평균 유동인구: https://www.data.go.kr/data/15098232/fileData.do
- 유성구 마을버스 정류장: https://www.data.go.kr/data/15023415/fileData.do
- 경찰서 현황: https://www.data.go.kr/data/15154551/fileData.do
- 비상벨 설치 현황: https://www.data.go.kr/data/15108941/fileData.do
- 50m 야간 유동인구: 유성구청 제공, 2025-08~2026-07, EPSG:5179

## 재현

`clean_new_sources.py`가 공공데이터 정제와 50m 원본 집계를 수행한다. 유성구청 원본 폴더 경로는 환경변수 `YUSEONG_FLOW_SOURCE_DIR`로 전달한다.
