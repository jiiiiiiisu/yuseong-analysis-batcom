# 유성구 야간 보행 안전 취약지역 분석 — 중간 전처리 결과

## 1. 프로젝트 목적

공공데이터를 수집·전처리하고 유성구 공식 행정경계와 결합하여, 중간보고회에서 현재까지의 데이터 확보·품질 점검·공간 분포를 설명할 수 있는 상태를 만드는 프로젝트입니다.

이번 단계에서는 종합 취약도 점수, 지표 가중치, 최종 정책 우선순위를 결정하지 않습니다. 생성된 지도는 시설과 야간 교통사고의 **현황 분포 또는 중첩 지도**이며 최종 취약지역 판정 결과가 아닙니다.

## 빠른 지도 보기

분석을 다시 실행하지 않아도 생성된 대화형 지도를 바로 확인할 수 있습니다.

- GitHub Pages 게시 주소: `https://jiiiiiiisu.github.io/yuseong-analysis-batcom/`

1. 저장소를 내려받거나 ZIP으로 다운로드합니다.
2. 프로젝트 최상위의 `index.html`을 더블클릭합니다.
3. 또는 `outputs/maps/yuseong_night_safety_map.html`을 직접 엽니다.

지도 오른쪽의 레이어 목록에서 CCTV 설치지점, 가로등, 버스정류장, 야간 교통사고, 경찰기관, 유동인구 레이어를 켜거나 끌 수 있습니다. CCTV 마커에는 해당 설치지점의 카메라 대수와 설치 목적이 표시됩니다. 지도 라이브러리와 배경지도를 외부에서 불러오므로 인터넷 연결이 필요합니다.

## 2. 현재 분석 범위와 진행 상태

- 원본 데이터 8종 전체 확보 및 `data_raw` 보존 완료(유동인구 1종은 사용자 수동 다운로드)
- 국가데이터처 SGIS 2025년 2분기 시군구·행정동 공식 경계 다운로드 및 안전 추출 완료
- CSV 7종과 유동인구 ZIP 1종의 실제 인코딩·컬럼·결측·중복·좌표 범위 조사 완료
- CCTV, 가로등, 버스정류장, 교통사고, 경찰기관 공간 전처리 완료
- 비상벨·유동인구·성연령 인구 행정동 집계 완료
- 정적 PNG 7개와 Folium 대화형 지도 생성 완료
- 유동인구 ZIP 12개월·156행을 통합하고 13개 행정동 요약 완료
- CCTV는 행정안전부 전국CCTV표준데이터의 유성구 기관별 CSV를 사용해 WGS84 좌표와 공식 경계를 검증 완료

## 3. 데이터 출처

| 번호 | 데이터 | 원본 링크 | 현재 상태 |
|---|---|---|---|
| 01 | 행정안전부 전국CCTV표준데이터(대전유성구) | https://www.data.go.kr/data/15013094/standard.do | WGS84·공식 경계 검증 완료 |
| 02 | 대전광역시 가로등 현황 | https://www.data.go.kr/data/15110054/fileData.do | 전처리 완료 |
| 03 | 전국 버스정류장 위치정보 | https://www.data.go.kr/data/15067528/fileData.do | 전처리 완료 |
| 04 | 인구 대비 동별 비상벨 현황 | https://www.data.go.kr/data/15111172/fileData.do | 전처리 완료 |
| 05 | 유성구 교통사고 현황 | https://www.data.go.kr/data/15108925/fileData.do | 전처리 완료 |
| 06 | 2023년 행정동별 일평균 유동인구 | https://www.data.go.kr/data/15139377/fileData.do | 수동 확보 및 전처리 완료 |
| 07 | 행정동별 성연령별 주민등록 인구 | https://www.data.go.kr/data/15108898/fileData.do | 전처리 완료 |
| 08 | 유성구 경찰서 현황 | https://www.data.go.kr/data/15154551/fileData.do | 전처리 완료 |
| 경계 | 국가데이터처 SGIS 행정구역 통계 및 경계 | https://www.data.go.kr/data/15129688/fileData.do | 2025년 2분기 경계 확보 |

## 4. 폴더 구조

```text
project_root/
├─ data_raw/                 # 다운로드 원본, 수정 금지
│  ├─ 01_cctv/
│  ├─ 02_streetlights/
│  ├─ 03_bus_stops/
│  ├─ 04_emergency_bells/
│  ├─ 05_traffic_accidents/
│  ├─ 06_floating_population/
│  ├─ 07_population/
│  ├─ 08_police_stations/
│  └─ boundary/
├─ data_clean/               # UTF-8 전처리 결과와 GeoJSON
├─ scripts/                  # 재현 가능한 Python 파이프라인
├─ outputs/
│  ├─ maps/                  # 발표용 PNG 및 대화형 HTML
│  ├─ tables/                # 점검·요약 CSV와 상태 워크북
│  └─ logs/                  # preprocessing.log
├─ notebooks/
├─ requirements.txt
└─ README.md
```

## 5. 설치 방법

Windows PowerShell 예시입니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 6. 실행 방법

전체 파이프라인을 순서대로 실행합니다. 특정 데이터가 없거나 개별 단계가 실패해도 다음 단계는 계속 진행하고 오류는 `outputs/logs/preprocessing.log`에 기록합니다.

```powershell
python scripts\run_all.py
```

단계별 실행도 가능합니다.

```powershell
python scripts\01_download_data.py
python scripts\02_inspect_raw_data.py
python scripts\03_preprocess_point_data.py
python scripts\04_preprocess_population_data.py
python scripts\05_create_static_maps.py
python scripts\06_create_interactive_map.py
python scripts\07_create_interim_summary.py
```

`01_download_data.py`는 현재 원본 파일의 존재 여부를 확인하고 SGIS 경계 ZIP에서 시군구·행정동 SHP 구성 파일만 Zip Slip 검증 후 추출합니다. 공공데이터포털의 동적 다운로드 자체는 브라우저에서 수행합니다.

## 7. 데이터별 전처리 기준

### CCTV

- 행정안전부 전국CCTV표준데이터 다운로드 화면에서 대전유성구 기관코드 `3670000`으로 받은 원본 580행, CP949
- 주소 580행 모두 유성구이며 WGS84 위·경도 결측·범위 오류·관리번호 중복은 0건
- SGIS 2025년 2분기 유성구 경계 내부 578개 설치지점을 확정하고, 경계 밖 좌표 2건은 제외
- 경계 내부 설치지점의 `카메라대수` 합계는 851대
- 원본의 `데이터기준일자`는 전부 2021-10-01이고 `데이터갱신시점` 최댓값은 2026-05-15이므로 최신 현장 상태는 별도 확인 필요
- 기존 유성구 파일의 불명확한 EPSG:2097 좌표에는 임의 오프셋을 적용하지 않고 `data_clean/01_cctv_legacy_epsg2097_audit.csv`로 감사용 보존

### 가로등

- 원본 43,082행, CP949
- `행정읍면동`에서 유성구 17,266행 1차 추출
- WGS84 좌표를 공식 유성구 경계로 재검증하여 17,101행 저장

### 버스정류장

- 원본 227,065행, CP949
- `도시명`·`관리도시명`으로 대전 3,245행을 먼저 추출
- 공식 유성구 경계 공간 필터 후 790행 저장

### 비상벨

- 법정동 61행을 행정동 13개로 집계
- 비상벨 수, 인구수, 인구 1,000명당 비상벨 수 계산
- 지점 좌표가 없으므로 GeoJSON을 만들지 않음

### 교통사고

- 원본 9,579행, CP949, EPSG:5179
- 공식 유성구 경계 내부 9,519행 확인
- `발생일시`의 시간이 20시 이상 **또는** 6시 미만인 경우 야간으로 정의
- 야간 사고 2,637행 저장

### 유동인구

- 원본 ZIP 내부 2023년 1~12월 CSV 12개를 경로 검증 후 안전 추출
- 실제 컬럼 `행정동`·`월`·`일평균`을 확인하고 156행을 통합
- 행정동 13개별 12개월 일평균의 평균·최솟값·최댓값을 산출하고 공식 경계와 전부 결합
- 공공데이터 설명상 KT 지침에 따라 시간대 자료는 제공되지 않음

### 성·연령별 주민등록 인구

- 원본 41,182행, CP949
- 최신 기준월 2022-01 자료를 사용
- 행정동 13개별 총인구, 여성인구·비율, 65세 이상 인구·비율 계산

### 경찰기관

- 원본 10행, CP949
- 실제 범위 조사 결과 원본 `위도`가 127.x, `경도`가 36.x로 컬럼 의미가 뒤바뀜
- 원본 `위도`를 경도, 원본 `경도`를 위도로 해석하여 공식 경계 재검증

## 8. 좌표계 처리 원칙

- 원본 메타데이터와 실제 좌표 범위를 함께 확인합니다.
- 거리·공간 연산: EPSG:5179
- 웹 지도·GeoJSON: EPSG:4326
- 투영 전후 좌표 범위와 처리 상태를 로그·점검표에 기록합니다.
- 좌표계가 불확실한 경우 임의 변환하지 않고 `needs_review`로 표시합니다.

## 9. 야간 사고 정의

```text
야간 사고 = 발생시간 >= 20:00 OR 발생시간 < 06:00
```

날짜가 바뀌는 구간이므로 `AND`가 아니라 `OR` 조건을 사용합니다.

## 10. 생성 결과

### 지도

- `outputs/maps/01_cctv_distribution.png` — 전국표준 WGS84 CCTV 설치지점 578개 분포
- `outputs/maps/02_streetlights_distribution.png`
- `outputs/maps/03_bus_stops_distribution.png`
- `outputs/maps/04_night_traffic_accidents.png`
- `outputs/maps/05_safety_facilities_combined.png`
- `outputs/maps/06_night_accidents_and_facilities.png`
- `outputs/maps/07_population_or_floating_population_by_dong.png`
- `outputs/maps/yuseong_night_safety_map.html`

### 표

- `outputs/tables/download_status.csv`
- `outputs/tables/raw_data_inventory.csv`
- `outputs/tables/raw_data_columns.csv`
- `outputs/tables/preprocessing_summary.csv`
- `outputs/tables/interim_data_summary.csv`
- `outputs/tables/key_statistics.csv`
- `outputs/tables/map_generation_status.csv`

## 11. 유동인구 원자료 보관 위치

사용자가 직접 내려받은 유동인구 ZIP을 아래 표준 경로에 보관했습니다.

```text
data_raw/06_floating_population/06_floating_population_by_dong.zip
```

`python scripts\run_all.py`를 다시 실행하면 ZIP 안전 추출부터 지도·요약표까지 재현됩니다.

## 12. 현재 한계

- 데이터별 기준 연도와 갱신 시점이 다릅니다.
- 가로등 수가 실제 밝기·점등 상태를 직접 의미하지 않습니다.
- CCTV 설치지점과 카메라 대수만으로 실제 촬영 범위·방향·가동 상태·사각지대를 설명할 수 없습니다.
- 유동인구는 행정동 단위 일평균 자료이므로 세부 위치와 야간 시간대 분석에는 한계가 있습니다.
- 경찰기관 파일의 위경도 컬럼명은 실제 값과 반대로 기록되어 있어 범위 검증 후 교정했습니다.
- 이번 결과는 시설 및 사고의 공간 분포를 확인하는 중간 결과이며 최종 취약지역 판정 결과가 아닙니다.

## 13. 다음 단계

1. 100m 또는 250m 격자 생성
2. CCTV 설치지점·카메라대수와 가로등의 밀도·최근접 거리 지표 산출
3. 야간 사고·보행수요 지표 산출
4. 동일 가중치와 조정 가중치 민감도 비교
5. 상위 후보지역 현장 또는 로드뷰 검증

## 14. 팀원 사용 매뉴얼

### 결과만 확인하는 경우

- 웹 지도: `index.html` 또는 `outputs/maps/yuseong_night_safety_map.html`
- 정적 지도: `outputs/maps/01_cctv_distribution.png`부터 `07_population_or_floating_population_by_dong.png`까지
- 핵심 통계: `outputs/tables/key_statistics.csv`
- 전체 중간 결과: `outputs/tables/yuseong_interim_status.xlsx`

### 분석을 다시 실행하는 경우

1. Python 가상환경을 만들고 `requirements.txt`를 설치합니다.
2. `data_raw`의 각 표준 경로에 원본 공공데이터가 있는지 확인합니다.
3. GitHub 용량 제한 때문에 제외된 SGIS 경계 ZIP을 데이터 출처 링크에서 내려받아 다음 위치에 둡니다.

   ```text
   data_raw/boundary/sgis_administrative_boundaries_2025.zip
   ```

4. `python scripts/run_all.py`를 실행합니다.
5. 실행 기록은 `outputs/logs/preprocessing.log`, 결과는 `data_clean`과 `outputs`에서 확인합니다.

## 15. GitHub 업로드 및 웹 게시

### 15.1 빈 저장소 만들기

GitHub에서 **New repository**를 선택하고 저장소 이름을 정합니다. 이 폴더에는 이미 README와 제외 목록이 있으므로 저장소를 만들 때 `Add a README file`, `.gitignore`, `License`는 추가하지 않습니다.

공개 저장소로 만들면 코드와 포함된 데이터가 인터넷에 공개됩니다. 업로드 전에 회의록, 개인 식별정보, 비공개 자료가 제외되었는지 반드시 확인합니다.

### 15.2 프로젝트 올리기

아래 명령을 프로젝트 최상위 폴더의 PowerShell에서 순서대로 실행합니다.

> 현재 이 프로젝트 폴더는 독립 Git 저장소가 아니므로 첫 번째 `git init`을 생략하지 마세요. 반드시 이 프로젝트 폴더에서 명령을 실행해야 다른 폴더의 파일이 섞이지 않습니다.

```powershell
git init
git branch -M main
git add .
git status
git commit -m "유성구 야간 보행 안전 분석 프로젝트 공유"
git remote add origin https://github.com/jiiiiiiisu/yuseong-analysis-batcom.git
git push -u origin main
```

`git status` 단계에서 `work`, `outputs/meeting_minutes`, `data_raw/boundary/extracted`가 보이지 않는지 확인합니다. 이 프로젝트에는 GitHub의 일반 업로드 한도를 초과하는 SGIS 원본 경계 파일이 있어 `.gitignore`로 제외했습니다.

### 15.3 GitHub Pages로 지도 공개하기

1. GitHub 저장소의 **Settings → Pages**로 이동합니다.
2. **Build and deployment → Source**에서 `Deploy from a branch`를 선택합니다.
3. 브랜치는 `main`, 폴더는 `/(root)`를 선택하고 **Save**를 누릅니다.
4. 배포가 끝나면 다음 형식의 주소로 지도를 공유할 수 있습니다.

   ```text
   https://jiiiiiiisu.github.io/yuseong-analysis-batcom/
   ```

GitHub Pages로 게시한 지도는 누구나 접속할 수 있는 공개 웹사이트가 될 수 있으므로 공개 가능한 데이터만 포함해야 합니다.
