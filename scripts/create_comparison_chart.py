import csv
import html
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path("data/predictions")
TEPCO_DIR = Path("data/predictions_tepco")
ACTUAL_DIR = Path("data/jepx/history")
OUTPUT_DIR = Path("data/comparison")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).date()


def load_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {
            int(row["period"]): row
            for row in csv.DictReader(f)
        }


def polyline(values, low, high):
    points = []
    for period in range(1, 49):
        value = values.get(period)
        if value is None:
            continue
        x = 65 + (period - 1) * 14
        y = 345 - (value - low) / (high - low) * 275
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def mae(predicted, actual):
    errors = [
        abs(predicted[p] - actual[p])
        for p in range(1, 49)
        if p in predicted and p in actual
    ]
    return sum(errors) / len(errors) if errors else None


def fmt(value):
    return f"{value:.2f}" if value is not None else "未取得"


def create_chart(date, baseline, adjusted, actual):
    values = list(baseline.values()) + list(adjusted.values())
    values += list(actual.values())

    low = min(values) - 2
    high = max(values) + 2
    if high <= low:
        high = low + 1

    base_mae = mae(baseline, actual)
    tepco_mae = mae(adjusted, actual)

    if base_mae is None or tepco_mae is None:
        verdict = "実績待ち：予測精度はまだ評価できません"
    elif tepco_mae < base_mae:
        verdict = "この日は東電PG連動予測の誤差が小さくなりました"
    elif tepco_mae > base_mae:
        verdict = "この日は従来予測の誤差が小さくなりました"
    else:
        verdict = "この日は両モデルの平均絶対誤差が同じでした"

    blue = polyline(baseline, low, high)
    green = polyline(adjusted, low, high)
    red = polyline(actual, low, high)

    page = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>JEPX 3モデル比較 {html.escape(date)}</title>
<style>
body {{
  font-family: sans-serif;
  background: #f3f6fa;
  padding: 16px;
}}
main {{
  max-width: 950px;
  margin: auto;
  background: white;
  padding: 20px;
  border-radius: 14px;
}}
svg {{ width: 100%; height: auto; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{
  padding: 8px;
  border-bottom: 1px solid #ddd;
  text-align: right;
}}
th:first-child, td:first-child {{ text-align: left; }}
.scroll {{ overflow-x: auto; }}
</style>
</head>
<body>
<main>
<h1>JEPX 東京エリア価格比較</h1>
<p>対象日：{html.escape(date)}</p>
<p>青：従来予測 ／ 緑：東電PG連動 ／ 赤：実績</p>
<p>従来予測 MAE：<strong>{fmt(base_mae)}</strong> 円/kWh</p>
<p>東電PG連動 MAE：<strong>{fmt(tepco_mae)}</strong> 円/kWh</p>
<p><strong>{html.escape(verdict)}</strong></p>
<svg viewBox="0 0 760 390" role="img" aria-label="3種類の価格比較">
<line x1="55" y1="345" x2="740" y2="345" stroke="#888"/>
<line x1="55" y1="65" x2="55" y2="345" stroke="#888"/>
<polyline points="{blue}" fill="none" stroke="#2563eb" stroke-width="2.5"/>
<polyline points="{green}" fill="none" stroke="#16a34a" stroke-width="2.5"/>
<polyline points="{red}" fill="none" stroke="#dc2626" stroke-width="2.5"/>
<text x="55" y="370">0:00</text>
<text x="360" y="370">12:00</text>
<text x="680" y="370">23:30</text>
<text x="60" y="45">円/kWh</text>
</svg>
<div class="scroll">
<table>
<tr>
<th>時間</th><th>従来予測</th>
<th>東電PG連動</th><th>実績</th>
</tr>
"""

    for period in range(1, 49):
        hour = (period - 1) // 2
        minute = 30 if period % 2 == 0 else 0
        page += (
            f"<tr><td>{hour:02d}:{minute:02d}</td>"
            f"<td>{fmt(baseline.get(period))}</td>"
            f"<td>{fmt(adjusted.get(period))}</td>"
            f"<td>{fmt(actual.get(period))}</td></tr>"
        )

    page += "</table></div></main></body></html>"
    return page


count = 0

for tepco_file in sorted(TEPCO_DIR.glob("*.csv")):
    date = tepco_file.stem
    base_file = BASE_DIR / tepco_file.name
    if not base_file.exists():
        continue

    base_rows = load_csv(base_file)
    tepco_rows = load_csv(tepco_file)

    if set(base_rows) != set(range(1, 49)):
        continue
    if set(tepco_rows) != set(range(1, 49)):
        continue

    baseline = {
        p: float(row["predicted_tokyo_yen_kwh"])
        for p, row in base_rows.items()
    }
    adjusted = {
        p: float(row["tepco_adjusted_yen_kwh"])
        for p, row in tepco_rows.items()
    }

    actual = {}
    actual_file = ACTUAL_DIR / tepco_file.name

    # Evaluate only after the target date has passed.
    target_date = datetime.strptime(date, "%Y-%m-%d").date()
    if target_date < today and actual_file.exists():
        actual_rows = load_csv(actual_file)
        actual = {
            p: float(row["tokyo_yen_kwh"])
            for p, row in actual_rows.items()
        }

    output = OUTPUT_DIR / f"{date}.html"
    output.write_text(
        create_chart(date, baseline, adjusted, actual),
        encoding="utf-8",
    )
    count += 1
    print(f"Saved: {output}")

print(f"Created {count} comparison charts")
