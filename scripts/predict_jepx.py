import csv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HISTORY = Path("data/jepx/history")
OUTPUT = Path("data/predictions")
OUTPUT.mkdir(parents=True, exist_ok=True)

jst = timezone(timedelta(hours=9))
today = datetime.now(jst).date()
target = today + timedelta(days=1)

prices = defaultdict(list)

for path in sorted(HISTORY.glob("*.csv")):
    try:
        day = datetime.strptime(path.stem, "%Y-%m-%d").date()
    except ValueError:
        continue

    if not (today - timedelta(days=6) <= day < target):
        continue

    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            period = int(row["period"])
            price = float(row["tokyo_yen_kwh"])
            if 1 <= period <= 48:
                prices[period].append(price)

if any(not prices[p] for p in range(1, 49)):
    raise ValueError("Insufficient JEPX history for 48 periods")

output = OUTPUT / f"{target.isoformat()}.csv"

with output.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.writer(file)
    writer.writerow([
        "target_date",
        "period",
        "predicted_tokyo_yen_kwh",
        "sample_count",
        "method"
    ])

    for period in range(1, 49):
        values = prices[period]
        predicted = round(sum(values) / len(values), 2)
        writer.writerow([
            target.isoformat(),
            period,
            predicted,
            len(values),
            "same_period_mean_7d"
        ])

print(f"Saved forecast: {output}")
print("Forecast periods: 48")
