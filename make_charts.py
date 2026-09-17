from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "analysis" / "01_admin_dong_risk_scores_draft.csv"
OUT = ROOT / "charts"
OUT.mkdir(exist_ok=True)

FONT_PATH = Path(r"C:\Windows\Fonts\malgun.ttf")
BOLD_PATH = Path(r"C:\Windows\Fonts\malgunbd.ttf")


def font(size: int, bold: bool = False):
    path = BOLD_PATH if bold and BOLD_PATH.exists() else FONT_PATH
    return ImageFont.truetype(str(path), size=size)


def text(draw, xy, value, size, fill="#222222", bold=False, anchor=None):
    draw.text(xy, str(value), font=font(size, bold), fill=fill, anchor=anchor)


df = pd.read_csv(DATA, encoding="utf-8-sig").sort_values("1차취약도점수", ascending=False).reset_index(drop=True)

# Ranking chart
w, h = 1600, 1100
img = Image.new("RGB", (w, h), "white")
draw = ImageDraw.Draw(img)
text(draw, (90, 65), "유성구 행정동별 야간안전 취약도 1차 분석", 48, bold=True)
text(draw, (92, 130), "중간보고용 초안 · 상위 3개 동 강조", 25, fill="#666666")
left, top, plot_w, row_h, bar_h = 300, 220, 1120, 62, 38
max_axis = 70
for tick in range(0, 71, 10):
    x = left + plot_w * tick / max_axis
    draw.line((x, top - 25, x, top + row_h * len(df)), fill="#e5e7eb", width=2)
    text(draw, (x, top - 42), tick, 21, fill="#6b7280", anchor="mm")
for idx, row in df.iterrows():
    y = top + idx * row_h
    text(draw, (95, y + bar_h / 2), f"{idx + 1}", 23, fill="#6b7280", anchor="lm")
    text(draw, (150, y + bar_h / 2), row["행정동이름"], 27, bold=idx < 3, anchor="lm")
    length = plot_w * float(row["1차취약도점수"]) / max_axis
    color = "#d73027" if idx < 3 else "#4575b4"
    draw.rounded_rectangle((left, y, left + length, y + bar_h), radius=7, fill=color)
    text(draw, (left + length + 14, y + bar_h / 2), f"{row['1차취약도점수']:.1f}", 23, anchor="lm")
text(draw, (left + plot_w / 2, h - 55), "1차 취약도 점수 (0~100)", 25, fill="#555555", anchor="mm")
img.save(OUT / "01_admin_dong_risk_ranking.png", quality=95)


# Top-five indicator heatmap
top5 = df.head(5)
cols = [
    ("유동인구_정규화", "유동인구"),
    ("취약인구_정규화", "취약인구"),
    ("비상벨부족_정규화", "비상벨 부족"),
    ("CCTV부족_정규화", "CCTV 부족"),
    ("야간사고_정규화", "야간사고"),
]
w, h = 1450, 760
img = Image.new("RGB", (w, h), "white")
draw = ImageDraw.Draw(img)
text(draw, (80, 55), "취약도 상위 5개 행정동의 지표 구성", 45, bold=True)
text(draw, (82, 115), "정규화 값이 높을수록 정책 우선순위가 증가", 24, fill="#666666")
left, top, cell_w, cell_h = 310, 230, 205, 82
for col, (_, label) in enumerate(cols):
    text(draw, (left + col * cell_w + cell_w / 2, top - 42), label, 25, anchor="mm")

def heat(value: float):
    low = (255, 255, 204)
    mid = (253, 141, 60)
    high = (177, 0, 38)
    if value <= 0.5:
        t = value / 0.5
        return tuple(int(low[i] + (mid[i] - low[i]) * t) for i in range(3))
    t = (value - 0.5) / 0.5
    return tuple(int(mid[i] + (high[i] - mid[i]) * t) for i in range(3))

for row_idx, (_, row) in enumerate(top5.iterrows()):
    y = top + row_idx * cell_h
    text(draw, (95, y + cell_h / 2), f"{row_idx + 1}위", 22, fill="#6b7280", anchor="lm")
    text(draw, (170, y + cell_h / 2), row["행정동이름"], 28, bold=True, anchor="lm")
    for col_idx, (column, _) in enumerate(cols):
        value = float(row[column])
        x = left + col_idx * cell_w
        draw.rectangle((x + 3, y + 3, x + cell_w - 3, y + cell_h - 3), fill=heat(value))
        text(draw, (x + cell_w / 2, y + cell_h / 2), f"{value:.2f}", 25, fill="white" if value > 0.55 else "#222222", anchor="mm")
text(draw, (left, h - 75), "낮음", 21, fill="#555555", anchor="lm")
for i in range(200):
    draw.line((left + 70 + i, h - 82, left + 70 + i, h - 52), fill=heat(i / 199), width=1)
text(draw, (left + 285, h - 75), "높음", 21, fill="#555555", anchor="lm")
img.save(OUT / "02_top5_indicator_profile.png", quality=95)
