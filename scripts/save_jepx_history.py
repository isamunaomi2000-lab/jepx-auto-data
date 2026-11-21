import csv
import io
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

URL = "https://japanesepower.org/jepxSpot.csv"
OUTPUT = Path("data/jepx/history")
OUTPUT.mkdir(parents=True, exist_ok=True)

request = urllib.request.Request(
    URL, headers={"User-Agent": "Mozilla/5.0"}
)
with urllib.request.urlopen(request, timeout=90) as response:
    content = response.read().decode("utf-8-sig")

rows = list(csv.DictReader(io.StringIO(content)))
if not rows:
    raise ValueError("JEPX CSV is empty")

by_day = defaultdict(dict)
for row in rows:
    day = row.get("Date", "").strip()
    period = row.get("PeriodID", "").strip()
    if day and period.isdigit() and 1 <= int(period) <= 48:
        by_day[day][int(period)] = row

jst = timezone(timedelta(hours=9))
start_date = (datetime.now(jst).date() - timedelta(days=6)).isoformat()
saved = 0

for day, periods in sorted(by_day.items()):
    if not (start_date <= day <= today) or len(periods) != 48:
        continue
    output_file = OUTPUT / f"{day}.csv"
    if output_file.exists():
        continue

    with output_file.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow([
            "date", "period", "tokyo_yen_kwh",
            "system_yen_kwh", "buy_bid_kwh",
            "sell_bid_kwh", "contracted_kwh"
        ])
        for period in range(1, 49):
            row = periods[period]
            writer.writerow([
                day,
                period,
                row["Tokyo Yen/kWh"],
                row["System Price Yen/kWh"],
                row["Buy Bid Volume kWh"],
                row["Sell Bid Volume kWh"],
                row["Contracted Total Volume kWh"]
            ])
    saved += 1

print(f"Saved {saved} daily JEPX files")
