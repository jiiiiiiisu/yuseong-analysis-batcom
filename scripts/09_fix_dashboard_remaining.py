from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

DASHBOARD = (
    ROOT
    / "outputs"
    / "maps"
    / "yuseong_night_safety_dashboard.html"
)


html = DASHBOARD.read_text(
    encoding="utf-8"
)


old = """      <div class="sp-row"><span>야간사고</span><b>${f.accident}건</b></div>"""

new = """      <div class="sp-row"><span>야간 유동인구</span><b>${f.population.toLocaleString()}명</b></div>
      <div class="sp-row"><span>비상벨 최근접</span><b>${f.bell_distance.toLocaleString()}m</b></div>
      <div class="sp-row"><span>경찰기관 최근접</span><b>${f.police_distance.toLocaleString()}m</b></div>"""


if old not in html:
    print(
        "수정 대상 야간사고 문구가 없습니다. "
        "이미 수정되었을 수 있습니다."
    )
else:
    html = html.replace(
        old,
        new,
        1,
    )

    DASHBOARD.write_text(
        html,
        encoding="utf-8",
    )

    print(
        "최종 후보 핀 Tooltip 수정 완료"
    )


# 최종 검증
html = DASHBOARD.read_text(
    encoding="utf-8"
)

remaining = (
    html.count("야간사고")
    + html.count("야간교통사고")
)

print(
    f"남은 화면용 사고 문구: {remaining}건"
)