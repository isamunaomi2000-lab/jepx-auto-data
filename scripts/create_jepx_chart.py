import csv
import html
import json
from pathlib import Path

PRED_DIR = Path("data/predictions")
ACTUAL_DIR = Path("data/jepx/history")
OUTPUT_DIR = Path("data/charts")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def read_prices(path, column):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {
            int(row["period"]): float(row[column])
            for row in csv.DictReader(f)
        }

def make_chart(date, predictions, actuals):
    periods = list(range(1, 49))
    pred = [predictions[p] for p in periods]
    actual = [actuals.get(p) for p in periods]

    available = [
        (p, a) for p, a in zip(pred, actual)
        if a is not None
    ]
    errors = [
        abs(p - a) for p, a in available
    ]
    mae = sum(errors) / len(errors) if errors else None

    all_values = pred + [a for a in actual if a is not None]
    low = min(all_values) - 2
    high = max(all_values) + 2
    if high <= low:
        high = low + 1

    def x(i):
        return 60 + i * 14

    def y(v):
        return 350 - (v - low) / (high - low) * 290

    def line(values):
        points = []
        for i, v in enumerate(values):
            if v is not None:
                points.append(f"{x(i):.1f},{y(v):.1f}")
        return " ".join(points)

    pred_line = line(pred)
    actual_line = line(actual)
    mae_text = f"{mae:.2f} 円/kWh" if mae is not None else "未評価"

    page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JEPX価格予測 {html.escape(date)}</title>
<style>
body {{ font-family: sans-serif; margin: 20px; background: #f7f9fc; }}
main {{ max-width: 900px; margin: auto; background: white; padding: 20px; border-radius: 12px; }}
svg {{ width: 100%; height: auto; }}
table {{ border-collapse: collapse; width: 100%; }}
th,td {{ padding: 8px; border-bottom: 1px solid #ddd; text-align: right; }}
th:first-child,td:first-child {{ text-align: left; }}
</style>
</head>
<body>
<main>
<h1>JEPX東京エリア価格比較</h1>
<p>対象日：{html.escape(date)}</p>
<p>平均絶対誤差（MAE）：<strong>{mae_text}</strong></p>
<p>青：予測価格　赤：実績価格</p>
<svg viewBox="0 0 760 400" role="img" aria-label="価格比較グラフ">
<line x1="50" y1="350" x2="740" y2="350" stroke="#888"/>
<line x1="50" y1="50" x2="50" y2="350" stroke="#888"/>
<polyline points="{pred_line}" fill="none" stroke="#2563eb" stroke-width="2.5"/>
<polyline points="{actual_line}" fill="none" stroke="#dc2626" stroke-width="2.5"/>
<text x="50" y="375">0:00</text>
<text x="360" y="375">12:00</text>
<text x="680" y="375">23:30</text>
<text x="55" y="40">円/kWh</text>
</svg>
<table>
<tr><th>時間帯</th><th>予測</th><th>実績</th><th>絶対誤差</th></tr>
"""
    for i, p in enumerate(periods):
        hour = (p - 1) // 2
        minute = 30 if p % 2 == 0 else 0
        a = actual[i]
        error = abs(pred[i] - a) if a is not None else None
        page += (
            f"<tr><td>{hour:02d}:{minute:02d}</td>"
            f"<td>{pred[i]:.2f}</td>"
            f"<td>{a:.2f}</td>" if a is not None else
            f"<tr><td>{hour:02d}:{minute:02d}</td>"
            f"<td>{pred[i]:.2f}</td><td>未取得</td>"
        )
        page += f"<td>{error:.2f}</td></tr>" if error is not None else "<td>—</td></tr>"

    page += "</table></main></body></html>"
    return page

for pred_file in sorted(PRED_DIR.glob("*.csv")):
    date = pred_file.stem
    predictions = read_prices(pred_file, "predicted_tokyo_yen_kwh")
    if not all(p in predictions for p in range(1, 49)):
        continue

    actual_file = ACTUAL_DIR / pred_file.name
    actuals = (
        read_prices(actual_file, "tokyo_yen_kwh")
        if actual_file.exists() else {}
    )

    output = OUTPUT_DIR / f"{date}.html"
    output.write_text(
        make_chart(date, predictions, actuals),
        encoding="utf-8"
    )
    print(f"Saved {output}")
