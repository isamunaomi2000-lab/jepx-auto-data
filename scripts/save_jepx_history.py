"""Keep the existing daily history format using verified JEPX official data."""
import csv
from datetime import datetime, timedelta
from pathlib import Path

from fetch_jepx import JST, load_days

OUTPUT = Path("data/jepx/history")


def main():
    today = datetime.now(JST).date()
    days, _, _, _ = load_days(today - timedelta(days=6), today)
    if today not in days:
        raise ValueError(f"JEPX official history has no complete day for {today}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for day, periods in sorted(days.items()):
        path = OUTPUT / f"{day}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow([
                "date", "period", "tokyo_yen_kwh", "system_yen_kwh",
                "buy_bid_kwh", "sell_bid_kwh", "contracted_kwh",
            ])
            for period, row in sorted(periods.items()):
                writer.writerow([day, period, *(
                    row[key] for key in ("tokyo", "system", "buy", "sell", "contracted")
                )])
    print(f"Verified {len(days)} complete daily JEPX files")


if __name__ == "__main__":
    main()
