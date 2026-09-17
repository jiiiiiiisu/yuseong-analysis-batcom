from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data_clean" / "09_admin_dong_base_table.csv"
OUT = ROOT / "analysis"
OUT.mkdir(exist_ok=True)


def minmax(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    lo, hi = x.min(), x.max()
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return pd.Series(0.5, index=series.index)
    return (x - lo) / (hi - lo)


df = pd.read_csv(SOURCE, encoding="utf-8-sig")

# Demand and vulnerability indicators: higher values mean a higher policy priority.
df["유동인구_정규화"] = minmax(df["연평균_일평균유동인구"])
df["여성비율_정규화"] = minmax(df["여성비율"])
df["고령인구비율_정규화"] = minmax(df["고령인구비율"])
df["취약인구_정규화"] = (df["여성비율_정규화"] + df["고령인구비율_정규화"]) / 2

# Infrastructure indicators are reversed: fewer facilities per population means higher priority.
df["비상벨부족_정규화"] = 1 - minmax(df["인구1만명당_비상벨수"])
df["CCTV부족_정규화"] = 1 - minmax(df["인구1만명당_CCTV지점수"])
df["야간사고_정규화"] = minmax(df["인구1만명당_야간교통사고수_2017_2021누적"])

weights = {
    "유동인구_정규화": 0.30,
    "취약인구_정규화": 0.25,
    "비상벨부족_정규화": 0.15,
    "CCTV부족_정규화": 0.20,
    "야간사고_정규화": 0.10,
}
df["1차취약도점수"] = sum(df[col] * weight for col, weight in weights.items()) * 100
df["1차취약도순위"] = df["1차취약도점수"].rank(method="min", ascending=False).astype(int)

# Equal-weight score is retained as a sensitivity check.
score_cols = list(weights)
df["동일가중치점수"] = df[score_cols].mean(axis=1) * 100
df["동일가중치순위"] = df["동일가중치점수"].rank(method="min", ascending=False).astype(int)
df["순위차이_민감도"] = (df["1차취약도순위"] - df["동일가중치순위"]).abs()

df = df.sort_values(["1차취약도순위", "행정동이름"])
df.to_csv(OUT / "01_admin_dong_risk_scores_draft.csv", index=False, encoding="utf-8-sig")

summary_cols = [
    "1차취약도순위",
    "행정동이름",
    "1차취약도점수",
    "동일가중치순위",
    "순위차이_민감도",
    "연평균_일평균유동인구",
    "여성비율",
    "고령인구비율",
    "인구1만명당_비상벨수",
    "인구1만명당_CCTV지점수",
    "인구1만명당_야간교통사고수_2017_2021누적",
]
summary = df[summary_cols].copy()
summary.to_csv(OUT / "02_admin_dong_ranking_summary.csv", index=False, encoding="utf-8-sig")

print(summary.to_string(index=False, formatters={"1차취약도점수": "{:.2f}".format}))
print("\n가중치:", weights)
print("최대 순위 민감도:", int(df["순위차이_민감도"].max()))
