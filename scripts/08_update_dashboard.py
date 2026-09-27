from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# 1. 경로 설정
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

ANALYSIS = ROOT / "analysis"
OUTPUTS = ROOT / "outputs" / "maps"

DASHBOARD = (
    OUTPUTS
    / "yuseong_night_safety_dashboard.html"
)

BACKUP = (
    OUTPUTS
    / "yuseong_night_safety_dashboard_before_population.html"
)

GRID_CSV = (
    ANALYSIS
    / "03_grid_500m_hotspot_scores.csv"
)

FINAL_CSV = (
    ANALYSIS
    / "10_final_policy_priority.csv"
)


# ============================================================
# 2. 입력 확인
# ============================================================

for path in [
    DASHBOARD,
    GRID_CSV,
    FINAL_CSV,
]:
    if not path.exists():
        raise FileNotFoundError(
            f"필요한 파일이 없습니다: {path}"
        )


# 기존 친구 대시보드 백업
# 최초 1회만 생성
if not BACKUP.exists():
    shutil.copy2(
        DASHBOARD,
        BACKUP,
    )


html = DASHBOARD.read_text(
    encoding="utf-8"
)


grid_df = pd.read_csv(
    GRID_CSV,
    encoding="utf-8-sig",
)

final_df = pd.read_csv(
    FINAL_CSV,
    encoding="utf-8-sig",
)


# ============================================================
# 3. 기존 HTML 안의 행정동 경계 추출
#
# 친구가 만든 지도/경계 데이터는 그대로 재사용한다.
# ============================================================

def extract_json_constant(
    text: str,
    name: str,
):
    pattern = (
        rf"const\s+{re.escape(name)}\s*=\s*"
        r"(\[.*?\]);"
    )

    match = re.search(
        pattern,
        text,
        flags=re.S,
    )

    if not match:
        raise RuntimeError(
            f"HTML에서 {name} 데이터를 찾지 못했습니다."
        )

    return json.loads(
        match.group(1)
    )


DONG_POLYS = extract_json_constant(
    html,
    "DONG_POLYS",
)


# ============================================================
# 4. 좌표 → 행정동 판정
# ============================================================

def point_in_polygon(
    lon: float,
    lat: float,
    polygon: list,
) -> bool:

    inside = False
    j = len(polygon) - 1

    for i in range(
        len(polygon)
    ):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        if (
            (yi > lat)
            != (yj > lat)
        ):
            intersect_lon = (
                (xj - xi)
                * (lat - yi)
                / (
                    (yj - yi)
                    or 1e-15
                )
                + xi
            )

            if lon < intersect_lon:
                inside = not inside

        j = i

    return inside


def distance_m(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:

    mean_lat = (
        lat1 + lat2
    ) / 2

    x = (
        (lon2 - lon1)
        * 111_320
        * math.cos(
            math.radians(
                mean_lat
            )
        )
    )

    y = (
        (lat2 - lat1)
        * 111_320
    )

    return math.sqrt(
        x * x + y * y
    )


def find_admin_dong(
    lon: float,
    lat: float,
) -> str:

    # 먼저 실제 행정동 polygon 내부인지 확인
    for dong in DONG_POLYS:
        pts = dong.get(
            "pts",
            [],
        )

        if (
            pts
            and point_in_polygon(
                lon,
                lat,
                pts,
            )
        ):
            return str(
                dong["name"]
            )

    # 경계선 등으로 정확히 포함되지 않는 경우
    # 가장 가까운 행정동 중심점을 사용
    nearest_name = ""
    nearest_distance = float(
        "inf"
    )

    for dong in DONG_POLYS:
        cx = float(
            dong.get(
                "cx",
                0,
            )
        )

        cy = float(
            dong.get(
                "cy",
                0,
            )
        )

        d = distance_m(
            lon,
            lat,
            cx,
            cy,
        )

        if d < nearest_distance:
            nearest_distance = d
            nearest_name = str(
                dong["name"]
            )

    return (
        nearest_name
        or "행정동 확인 필요"
    )


# ============================================================
# 5. 새 609개 격자 데이터 구성
# ============================================================

required_grid_columns = [
    "중심경도",
    "중심위도",
    "격자취약도점수",
    "격자취약도순위",
    "안전수요점수",
    "시설공백점수",
    "야간유동인구",
    "버스정류장수",
    "CCTV수",
    "가로등수",
    "보안등수",
    "조명시설수",
]

missing = [
    col
    for col in required_grid_columns
    if col not in grid_df.columns
]

if missing:
    raise KeyError(
        "격자 결과에 필요한 열이 없습니다: "
        + ", ".join(missing)
    )


grid_df = grid_df.copy()

grid_df["행정동"] = [
    find_admin_dong(
        float(lon),
        float(lat),
    )
    for lon, lat
    in zip(
        grid_df["중심경도"],
        grid_df["중심위도"],
    )
]


grid_records = []

for _, row in grid_df.iterrows():

    grid_records.append(
        {
            "lon": round(
                float(
                    row["중심경도"]
                ),
                6,
            ),

            "lat": round(
                float(
                    row["중심위도"]
                ),
                6,
            ),

            "score": round(
                float(
                    row["격자취약도점수"]
                ),
                2,
            ),

            "demand": round(
                float(
                    row["안전수요점수"]
                ),
                4,
            ),

            "gap": round(
                float(
                    row["시설공백점수"]
                ),
                4,
            ),

            "population": round(
                float(
                    row["야간유동인구"]
                ),
                2,
            ),

            "cctv": int(
                row["CCTV수"]
            ),

            "light": int(
                row["가로등수"]
            ),

            "seclight": int(
                row["보안등수"]
            ),

            "facility": int(
                row["조명시설수"]
            ),

            "bus": int(
                row["버스정류장수"]
            ),

            "rank": int(
                row["격자취약도순위"]
            ),

            "admin_dong": str(
                row["행정동"]
            ),
        }
    )


# ============================================================
# 6. 새 행정동 요약
#
# 기존 사고기반 행정동 점수는 사용하지 않는다.
#
# 새 500m 취약도 결과를 행정동별 평균으로 요약한다.
# 이 값은 대시보드 요약용이며 최종 정책순위는
# 500m 격자 순위를 그대로 사용한다.
# ============================================================

dong_summary = (
    grid_df.groupby(
        "행정동",
        as_index=False,
    )
    .agg(
        score=(
            "격자취약도점수",
            "mean",
        ),
        grid_count=(
            "격자취약도점수",
            "size",
        ),
        population=(
            "야간유동인구",
            "sum",
        ),
        cctv=(
            "CCTV수",
            "sum",
        ),
        lighting=(
            "조명시설수",
            "sum",
        ),
        bus=(
            "버스정류장수",
            "sum",
        ),
    )
)


dong_summary = (
    dong_summary.sort_values(
        "score",
        ascending=False,
    )
    .reset_index(
        drop=True
    )
)


dong_summary["rank"] = (
    np.arange(
        len(dong_summary)
    )
    + 1
)


dong_records = []

for _, row in dong_summary.iterrows():

    dong_records.append(
        {
            "rank": int(
                row["rank"]
            ),

            "name": str(
                row["행정동"]
            ),

            "score": round(
                float(
                    row["score"]
                ),
                1,
            ),

            "grid_count": int(
                row["grid_count"]
            ),

            "population": round(
                float(
                    row["population"]
                ),
                1,
            ),

            "cctv": int(
                row["cctv"]
            ),

            "lighting": int(
                row["lighting"]
            ),

            "bus": int(
                row["bus"]
            ),
        }
    )


# ============================================================
# 7. 새 Top 10 정책 후보 데이터 구성
# ============================================================

required_final_columns = [
    "최종순위",
    "정책우선등급",
    "후보지역",
    "중심경도",
    "중심위도",
    "야간유동인구",
    "버스정류장수",
    "CCTV수",
    "가로등수",
    "보안등수",
    "조명시설수",
    "최종취약도점수",
    "정책유형",
    "권장정책",
    "선정근거",
    "최근접_비상벨거리_m",
    "반경500m_비상벨수",
    "최근접_경찰기관거리_m",
]

missing = [
    col
    for col in required_final_columns
    if col not in final_df.columns
]

if missing:
    raise KeyError(
        "최종 후보 결과에 필요한 열이 없습니다: "
        + ", ".join(missing)
    )


final_df = (
    final_df.sort_values(
        "최종순위"
    )
    .head(10)
    .copy()
)


final_records = []

for _, row in final_df.iterrows():

    lon = float(
        row["중심경도"]
    )

    lat = float(
        row["중심위도"]
    )

    final_records.append(
        {
            "rank": int(
                row["최종순위"]
            ),

            "grade": str(
                row["정책우선등급"]
            ),

            "site": str(
                row["후보지역"]
            ),

            "lon": round(
                lon,
                6,
            ),

            "lat": round(
                lat,
                6,
            ),

            "population": round(
                float(
                    row["야간유동인구"]
                ),
                2,
            ),

            "cctv": int(
                row["CCTV수"]
            ),

            "light": int(
                row["가로등수"]
            ),

            "seclight": int(
                row["보안등수"]
            ),

            "facility": int(
                row["조명시설수"]
            ),

            "bus": int(
                row["버스정류장수"]
            ),

            "score": round(
                float(
                    row["최종취약도점수"]
                ),
                2,
            ),

            "type": str(
                row["정책유형"]
            ),

            "policy": str(
                row["권장정책"]
            ),

            "reason": str(
                row["선정근거"]
            ),

            "bell_distance": round(
                float(
                    row[
                        "최근접_비상벨거리_m"
                    ]
                ),
                1,
            ),

            "bell_500m": int(
                row[
                    "반경500m_비상벨수"
                ]
            ),

            "police_distance": round(
                float(
                    row[
                        "최근접_경찰기관거리_m"
                    ]
                ),
                1,
            ),

            "admin_dong": (
                find_admin_dong(
                    lon,
                    lat,
                )
            ),
        }
    )


# ============================================================
# 8. HTML 속 JavaScript 데이터 배열 교체
# ============================================================

def replace_js_constant(
    text: str,
    name: str,
    value,
) -> str:

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(
            ",",
            ":",
        ),
    )

    pattern = (
        rf"const\s+{re.escape(name)}\s*="
        r"\s*\[.*?\];"
    )

    replacement = (
        f"const {name} = "
        f"{encoded};"
    )

    new_text, count = re.subn(
        pattern,
        replacement,
        text,
        count=1,
        flags=re.S,
    )

    if count != 1:
        raise RuntimeError(
            f"{name} 배열 교체 실패"
        )

    return new_text


html = replace_js_constant(
    html,
    "GRIDS",
    grid_records,
)

html = replace_js_constant(
    html,
    "FINAL",
    final_records,
)

html = replace_js_constant(
    html,
    "DONG",
    dong_records,
)


# ============================================================
# 9. 화면 상단 설명/KPI 교체
# ============================================================

# 분석 격자 개수
html = re.sub(
    r"<span><b>분석 단위</b>&nbsp;"
    r"500m 격자 · \d+개</span>",
    (
        "<span><b>분석 단위</b>&nbsp;"
        f"500m 격자 · {len(grid_df):,}개</span>"
    ),
    html,
    count=1,
)


# 데이터 기준 안내
html = re.sub(
    r'<div class="vintage-note">.*?</div>',
    """
  <div class="vintage-note">
    <b>최종 분석 기준</b> —
    유성구청 제공 2025-08~2026-07
    22:00~06:00 야간 유동인구와
    CCTV·가로등·보안등·마을버스 정류장을
    500m 격자 단위로 결합했다.
    경찰기관·비상벨은 <b>취약도 점수에 포함하지 않고
    대응 접근성 검토에만 활용</b>했다.
  </div>
""",
    html,
    count=1,
    flags=re.S,
)


# Hero 문구
html = html.replace(
    """<h1>가로등이 닿지 않는 곳에서<br>다음 사고가 <em>시작</em>된다</h1>""",
    """<h1>야간 활동수요와<br>안전시설 <em>공백</em>을 함께 본다</h1>""",
)


html = re.sub(
    r'<p class="lede">.*?</p>',
    """
        <p class="lede">
          유성구청 야간 유동인구·마을버스 정류장으로
          야간 안전수요를 산정하고,
          CCTV·가로등·보안등의 시설공백을 결합해
          500m 격자별 야간 보행안전 취약도를 분석했다.
        </p>
""",
    html,
    count=1,
    flags=re.S,
)


# Top10 등급 개수
grade_counts = (
    final_df[
        "정책우선등급"
    ]
    .value_counts()
    .to_dict()
)

a_count = int(
    grade_counts.get(
        "A",
        0,
    )
)

b_count = int(
    grade_counts.get(
        "B",
        0,
    )
)

c_count = int(
    grade_counts.get(
        "C",
        0,
    )
)


html = re.sub(
    r'<div class="cap">최종 정책 우선<br>'
    r'후보지 \(A .*?</div>',
    (
        '<div class="cap">'
        '최종 정책 우선<br>'
        f'후보지 (A {a_count} · '
        f'B {b_count} · '
        f'C {c_count}등급)'
        '</div>'
    ),
    html,
    count=1,
)


# KPI 교체 함수
def replace_kpi(
    text: str,
    old_label: str,
    new_html: str,
) -> str:

    pattern = (
        r'<div class="kpi">'
        rf'<div class="label">{re.escape(old_label)}</div>'
        r'.*?</div></div>'
    )

    new_text, count = re.subn(
        pattern,
        new_html,
        text,
        count=1,
        flags=re.S,
    )

    if count == 0:
        print(
            f"[주의] KPI '{old_label}'를 찾지 못했습니다."
        )

    return new_text


html = replace_kpi(
    html,
    "분석 대상 인구",
    f"""
      <div class="kpi">
        <div class="label">야간 유동인구 격자</div>
        <div class="value tnum">{len(grid_df):,}<span>개</span></div>
        <div class="sub">12개월 확보 · 500m 분석대상</div>
      </div>
""",
)


html = replace_kpi(
    html,
    "분석 격자",
    """
      <div class="kpi">
        <div class="label">마을버스 정류장</div>
        <div class="value tnum">264<span>개소</span></div>
        <div class="sub">정류장 위치 기준 정제</div>
      </div>
""",
)


html = replace_kpi(
    html,
    "CCTV",
    """
      <div class="kpi">
        <div class="label">CCTV</div>
        <div class="value tnum">668<span>개소</span></div>
        <div class="sub">분석 경계 내 사용</div>
      </div>
""",
)


html = replace_kpi(
    html,
    "보안등",
    """
      <div class="kpi">
        <div class="label">보안등</div>
        <div class="value tnum">3,969<span>개</span></div>
        <div class="sub">설치개수 합계</div>
      </div>
""",
)


html = replace_kpi(
    html,
    "야간교통사고",
    """
      <div class="kpi">
        <div class="label">가로등</div>
        <div class="value tnum">17,032<span>개</span></div>
        <div class="sub">유성구 분석 사용자료</div>
      </div>
""",
)


html = replace_kpi(
    html,
    "비상벨",
    """
      <div class="kpi">
        <div class="label">비상벨</div>
        <div class="value tnum">145<span>개소</span></div>
        <div class="sub">대응 접근성 보조지표</div>
      </div>
""",
)


# ============================================================
# 10. 메뉴/본문 설명 교체
# ============================================================

html = html.replace(
    '<option value="dong">행정동 순위</option>',
    '<option value="dong">행정동 평균 취약도</option>',
)


html = html.replace(
    "행정동별 1차 취약도 순위",
    "행정동별 평균 격자취약도",
)


html = re.sub(
    (
        r"<p>유동인구·취약인구 비율과 "
        r"비상벨·CCTV 부족도, 야간사고 누적치를 "
        r"결합한 1차 스코어\..*?</p>"
    ),
    """
          <p>
            새 500m 격자 취약도 점수를 행정동별로 평균한
            대시보드 요약값이다.
            최종 정책 후보 순위는 행정동 평균이 아니라
            500m 격자별 취약도 순위를 사용한다.
          </p>
""",
    html,
    count=1,
    flags=re.S,
)


html = re.sub(
    (
        r"<p>등급별로 권장 정책 방향이 다르다 — "
        r"A는 시설 자체가 없는 공백지,.*?</p>"
    ),
    """
          <p>
            A는 CCTV·조명시설이 모두 없는 시설공백형,
            B는 CCTV 또는 조명 중 특정 시설의 보완이 필요한 지역,
            C는 시설이 존재하지만 야간 활동수요가 높아
            보행환경·시설운영 관리가 필요한 지역이다.
          </p>
""",
    html,
    count=1,
    flags=re.S,
)


# 방법론
html = re.sub(
    (
        r"<p>① 행정동 단위 1차 취약도 스코어링.*?</p>"
    ),
    """
          <p>
            ① 유성구청 22:00~06:00 야간 유동인구를
            500m 격자에 결합 →
            ② 야간유동인구 60% + 버스정류장 40%로
            안전수요 산정 →
            ③ CCTV 부족 55% + 조명시설 부족 45%로
            시설공백 산정 →
            ④ 안전수요 65% + 시설공백 35%로
            최종 취약도 산정 →
            ⑤ 상위 10개 후보의 비상벨·경찰기관
            접근성을 별도 검토.
          </p>
""",
    html,
    count=1,
    flags=re.S,
)


# 사고 데이터 출처 제거
html = html.replace(
    """            <li>야간교통사고 2017–2021 (경찰청)</li>
""",
    "",
)


# ============================================================
# 11. JavaScript 행정동 Tooltip 수정
# ============================================================

old_admin_tooltip = """      const infoHtml = `
        <div class="sp-title">${d.name} · 행정동 전체 ${d.rank}위</div>
        <div class="sp-row"><span>1차 취약도 점수</span><b>${d.score.toFixed(1)}</b></div>
        <div class="sp-row"><span>일평균 유동인구</span><b>${d.pop_flow.toLocaleString()}명</b></div>
        <div class="sp-row"><span>고령인구비율</span><b>${d.elder_ratio}%</b></div>
        <div class="sp-row"><span>인구 1만명당 야간사고</span><b>${d.accident_per10k}</b></div>
      `;"""


new_admin_tooltip = """      const infoHtml = `
        <div class="sp-title">${d.name} · 평균 격자취약도 ${d.rank}위</div>
        <div class="sp-row"><span>평균 취약도</span><b>${d.score.toFixed(1)}</b></div>
        <div class="sp-row"><span>분석 격자</span><b>${d.grid_count}개</b></div>
        <div class="sp-row"><span>야간 유동인구 합계</span><b>${d.population.toLocaleString()}명</b></div>
        <div class="sp-row"><span>CCTV</span><b>${d.cctv}개</b></div>
        <div class="sp-row"><span>조명시설</span><b>${d.lighting}개</b></div>
        <div class="sp-row"><span>버스정류장</span><b>${d.bus}개</b></div>
      `;"""


if old_admin_tooltip not in html:
    raise RuntimeError(
        "행정동 지도 Tooltip 부분을 찾지 못했습니다."
    )

html = html.replace(
    old_admin_tooltip,
    new_admin_tooltip,
    1,
)


# ============================================================
# 12. 격자 Tooltip 수정
# ============================================================

old_grid_tooltip = """    const legalRow = g.near_legal_dist > 800
      ? `<div class="sp-row"><span>최근접 법정동</span><b style="color:var(--text-muted)">${g.near_legal} (${g.near_legal_dist}m, 다소 먼 거리)</b></div>`
      : `<div class="sp-row"><span>최근접 법정동</span><b>${g.near_legal} (${g.near_legal_dist}m)</b></div>`;
    const infoHtml = `
      <div class="sp-title">${g.admin_dong} · 격자취약도 ${g.rank}위</div>
      ${legalRow}
      <div class="sp-row"><span>좌표</span><b>${g.lat.toFixed(5)}, ${g.lon.toFixed(5)}</b></div>
      <div class="sp-row"><span>취약도 점수</span><b>${g.score.toFixed(1)}</b></div>
      <div class="sp-row"><span>CCTV</span><b>${g.cctv}</b></div>
      <div class="sp-row"><span>가로등 / 보안등</span><b>${g.light} / ${g.seclight}</b></div>
      <div class="sp-row"><span>버스정류장</span><b>${g.bus}</b></div>
      <div class="sp-row"><span>야간사고</span><b>${g.accident}건</b></div>
    `;"""


new_grid_tooltip = """    const infoHtml = `
      <div class="sp-title">${g.admin_dong} · 격자취약도 ${g.rank}위</div>
      <div class="sp-row"><span>좌표</span><b>${g.lat.toFixed(5)}, ${g.lon.toFixed(5)}</b></div>
      <div class="sp-row"><span>취약도 점수</span><b>${g.score.toFixed(1)}</b></div>
      <div class="sp-row"><span>야간 유동인구</span><b>${g.population.toLocaleString()}명</b></div>
      <div class="sp-row"><span>안전수요점수</span><b>${g.demand.toFixed(3)}</b></div>
      <div class="sp-row"><span>시설공백점수</span><b>${g.gap.toFixed(3)}</b></div>
      <div class="sp-row"><span>CCTV</span><b>${g.cctv}</b></div>
      <div class="sp-row"><span>가로등 / 보안등</span><b>${g.light} / ${g.seclight}</b></div>
      <div class="sp-row"><span>버스정류장</span><b>${g.bus}</b></div>
    `;"""


if old_grid_tooltip not in html:
    raise RuntimeError(
        "격자 Tooltip 부분을 찾지 못했습니다."
    )

html = html.replace(
    old_grid_tooltip,
    new_grid_tooltip,
    1,
)


# ============================================================
# 13. 행정동 막대그래프 Tooltip 수정
# ============================================================

old_dong_bar_tooltip = """    fill.addEventListener('mousemove',(e)=> showTT(e, `
      <div class="tt-title">${d.name} · 전체 ${d.rank}위</div>
      <div class="tt-row"><span>일평균 유동인구</span><b>${d.pop_flow.toLocaleString()}명</b></div>
      <div class="tt-row"><span>여성비율</span><b>${d.female_ratio}%</b></div>
      <div class="tt-row"><span>고령인구비율</span><b>${d.elder_ratio}%</b></div>
      <div class="tt-row"><span>인구 1만명당 CCTV</span><b>${d.cctv_per10k}</b></div>
      <div class="tt-row"><span>인구 1만명당 비상벨</span><b>${d.bell_per10k}</b></div>
      <div class="tt-row"><span>인구 1만명당 야간사고(17-21누적)</span><b>${d.accident_per10k}</b></div>
    `));"""


new_dong_bar_tooltip = """    fill.addEventListener('mousemove',(e)=> showTT(e, `
      <div class="tt-title">${d.name} · 평균 격자취약도 ${d.rank}위</div>
      <div class="tt-row"><span>평균 취약도</span><b>${d.score.toFixed(1)}</b></div>
      <div class="tt-row"><span>분석 격자</span><b>${d.grid_count}개</b></div>
      <div class="tt-row"><span>야간 유동인구 합계</span><b>${d.population.toLocaleString()}명</b></div>
      <div class="tt-row"><span>CCTV</span><b>${d.cctv}개</b></div>
      <div class="tt-row"><span>조명시설</span><b>${d.lighting}개</b></div>
      <div class="tt-row"><span>버스정류장</span><b>${d.bus}개</b></div>
    `));"""


if old_dong_bar_tooltip not in html:
    raise RuntimeError(
        "행정동 그래프 Tooltip 부분을 찾지 못했습니다."
    )

html = html.replace(
    old_dong_bar_tooltip,
    new_dong_bar_tooltip,
    1,
)

# ============================================================
# 13-1. 지도 위 Top10 후보 핀 Tooltip 수정
# ============================================================

old_final_pin_tooltip = """      <div class="sp-row"><span>야간사고</span><b>${f.accident}건</b></div>"""

new_final_pin_tooltip = """      <div class="sp-row"><span>야간 유동인구</span><b>${f.population.toLocaleString()}명</b></div>
      <div class="sp-row"><span>비상벨 최근접</span><b>${f.bell_distance.toLocaleString()}m</b></div>
      <div class="sp-row"><span>경찰기관 최근접</span><b>${f.police_distance.toLocaleString()}m</b></div>"""

if old_final_pin_tooltip in html:
    html = html.replace(
        old_final_pin_tooltip,
        new_final_pin_tooltip,
        1,
    )
# ============================================================
# 14. Top10 카드에서 사고 제거 → 유동인구/대응접근성
# ============================================================

old_chip = """        <div class="accident-chip"><i></i>야간사고 누적 ${f.accident}건</div>"""

new_chip = """        <div class="accident-chip"><i></i>야간 유동인구 ${f.population.toLocaleString()}명</div>"""


if old_chip not in html:
    raise RuntimeError(
        "Top10 사고 표시 부분을 찾지 못했습니다."
    )

html = html.replace(
    old_chip,
    new_chip,
    1,
)


# 정책 카드에 대응 접근성 추가
old_policy = """      <div class="cand-policy">
        <div class="label">권장 정책</div>
        <div class="val">${f.policy}</div>
      </div>"""


new_policy = """      <div class="cand-policy">
        <div class="label">권장 정책</div>
        <div class="val">${f.policy}</div>
        <div class="reason" style="margin-top:7px">
          비상벨 ${f.bell_distance.toLocaleString()}m ·
          500m 내 ${f.bell_500m}개<br>
          경찰기관 ${f.police_distance.toLocaleString()}m
        </div>
      </div>"""


if old_policy not in html:
    raise RuntimeError(
        "Top10 정책 표시 부분을 찾지 못했습니다."
    )

html = html.replace(
    old_policy,
    new_policy,
    1,
)


# 등급 설명
html = re.sub(
    r"const GRADE_LABEL = \{.*?\};",
    (
        "const GRADE_LABEL = "
        "{A:'시설공백 최우선', "
        "B:'시설 보완', "
        "C:'야간안심보행 관리'};"
    ),
    html,
    count=1,
)


# ============================================================
# 15. 남은 사용자 화면용 사고 문구 제거
# ============================================================

html = html.replace(
    "CCTV·가로등·보안등·버스정류장·야간교통사고 등",
    "CCTV·가로등·보안등·버스정류장·야간 유동인구 등",
)

html = html.replace(
    "CCTV/night-accident/emergency-bell points",
    "CCTV/emergency-bell points",
)


# ============================================================
# 16. 최종 저장
# ============================================================

DASHBOARD.write_text(
    html,
    encoding="utf-8",
)


# ============================================================
# 17. 검증
# ============================================================

remaining_korean_accident = (
    html.count(
        "야간사고"
    )
    + html.count(
        "야간교통사고"
    )
)


print()
print("=" * 80)
print(
    "유성구 야간안전 대시보드 업데이트 완료"
)
print("=" * 80)

print(
    f"격자 데이터: {len(grid_records):,}개"
)

print(
    f"행정동 요약: {len(dong_records):,}개"
)

print(
    f"최종 후보: {len(final_records):,}개"
)

print(
    "취약도 기준: "
    "야간유동인구 + 버스정류장 + "
    "CCTV부족 + 조명시설부족"
)

print(
    "경찰기관·비상벨: "
    "점수 제외 / 대응 접근성 검토만 사용"
)

print(
    f"남은 화면용 사고 문구: "
    f"{remaining_korean_accident}건"
)

print()
print(
    f"대시보드: {DASHBOARD}"
)

print(
    f"기존본 백업: {BACKUP}"
)