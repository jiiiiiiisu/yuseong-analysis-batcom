from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
ANALYSIS = ROOT / "analysis"

LABELS = {
    (6, 0): "진잠동 계백로",
    (18, 18): "원신흥동 갑천 자전거길",
    (13, 7): "원내동 계백로",
    (27, 35): "용산동 테크노중앙로",
    (26, 24): "도룡동 엑스포로",
    (16, 32): "자운동 자운로97번길",
    (17, 21): "궁동 대학로81번길",
    (11, 29): "반석동 반석서로83번길",
    (18, 20): "봉명동 온천북로59번길",
    (15, 20): "구암동 계룡로",
}


def classify(row):
    if row["CCTV수"] == 0 and row["조명시설수"] == 0:
        return "시설공백 최우선", "보안등·CCTV 배치 타당성 검토"
    if row["CCTV수"] == 0:
        return "CCTV 보완", "기존 조명 활용 + CCTV 사각지대 보완"
    if row["야간사고수"] >= 40:
        return "교통·보행안전", "횡단·속도·정류장 동선 중심 안전개선"
    return "복합 관리", "시설 운영상태와 사고지점 맞춤 개선"


def evidence(row):
    parts = []
    if row["CCTV수"] == 0:
        parts.append("격자 내 CCTV 0")
    if row["조명시설수"] == 0:
        parts.append("격자 내 가로등·보안등 0")
    if row["버스정류장수"] >= 5:
        parts.append(f"정류장 {int(row['버스정류장수'])}개")
    if row["야간사고수"] >= 20:
        parts.append(f"야간사고 {int(row['야간사고수'])}건")
    if not parts:
        parts.append("수요·시설 복합점수 상위")
    return ", ".join(parts)


top = pd.read_csv(
    ANALYSIS / "08_top10_hotspots_with_security_lights.csv", encoding="utf-8-sig"
).copy()
top["후보지역"] = [LABELS[(int(x), int(y))] for x, y in zip(top["grid_x"], top["grid_y"])]
classified = top.apply(classify, axis=1, result_type="expand")
top["정책유형"] = classified[0]
top["권장정책"] = classified[1]
top["선정근거"] = top.apply(evidence, axis=1)
top["정책우선등급"] = top["정책유형"].map(
    {"시설공백 최우선": "A", "CCTV 보완": "B", "교통·보행안전": "C", "복합 관리": "C"}
)

result = top[
    [
        "격자취약도순위_보완",
        "정책우선등급",
        "후보지역",
        "중심경도",
        "중심위도",
        "CCTV수",
        "가로등수",
        "보안등수",
        "조명시설수",
        "버스정류장수",
        "야간사고수",
        "격자취약도점수_보완",
        "정책유형",
        "권장정책",
        "선정근거",
    ]
].rename(columns={"격자취약도순위_보완": "최종순위", "격자취약도점수_보완": "최종취약도점수"})
result["최종취약도점수"] = result["최종취약도점수"].round(2)
result.to_csv(ANALYSIS / "10_final_policy_priority.csv", index=False, encoding="utf-8-sig")

summary = f"""# 유성구 야간안전 취약지역 데이터 기반 최종 후보안

## 결론

- 시설공백 최우선 검토: 진잠동 계백로, 자운동 자운로97번길
- CCTV 보완 검토: 원신흥동 갑천 자전거길, 용산동 테크노중앙로, 도룡동 엑스포로
- 교통·보행안전 중심 개선: 원내동 계백로, 궁동 대학로81번길, 반석동 반석서로83번길, 봉명동 온천북로59번길, 구암동 계룡로

## 핵심 해석

1. 진잠동 계백로는 보안등을 반영한 뒤에도 최종 1위다. 후보 중심 500m 안에는 보안등이 12개 있으므로 ‘무조명 지역’이 아니라 수요와 사고 대비 시설 배치가 상대적으로 취약한 지역으로 해석해야 한다.
2. 자운동 자운로97번길은 분석 격자 내 CCTV·가로등·보안등이 모두 0이며, 후보 중심 1km 안에서도 보안등이 확인되지 않아 시설공백형 후보로 남는다.
3. 원신흥동·용산동·도룡동은 조명시설이 존재하지만 격자 내 CCTV가 0이므로 조명 신설보다 CCTV 사각지대 검토가 우선이다.
4. 궁동·봉명동·구암동 등은 조명과 CCTV가 존재하면서 야간사고와 이용수요가 높다. 시설 수량 확대보다 횡단·속도·정류장 동선 등 교통·보행안전 정책이 적절하다.

## 분석 한계

- 보안등 API 기준일은 2022-06-15이다.
- 현재 격자 경계는 OpenStreetMap 기반 작업용 유성구 경계를 사용했다. 최종 공식 제출 시 SGIS 또는 VWorld 공식 경계로 재검증하는 것이 바람직하다.
- 본 순위는 범죄발생 가능성을 예측하는 값이 아니라 안전시설과 보행환경 개선을 위한 상대적 정책 우선순위다.

## 데이터 출처

- 대전광역시 보안등조회서비스: https://www.data.go.kr/data/15110685/openapi.do
- 기타 원자료 및 분석 과정: ../README.md
"""
(ANALYSIS / "11_final_policy_summary.md").write_text(summary, encoding="utf-8")
print(result.to_string(index=False))


if __name__ == "__main__":
    pass
