import csv
import io
import json
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

URL = "https://japanesepower.org/jepxSpot.csv"
AREAS = {
    "system": "System Price Yen/kWh",
    "tokyo": "Tokyo Yen/kWh",
    "kansai": "Kansai Yen/kWh",
    "kyushu": "Kyushu Yen/kWh",
}

def main():
    request = urllib.request.Request(
        URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        text = response.read().decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("CSV is empty")

    by_day = defaultdict(dict)
    for row in rows:
        date = row.get("Date", "").strip()
        period = row.get("PeriodID", "").strip()
        if date and period:
            by_day[date][period] = row

    complete = sorted(
        d for d, periods in by_day.items()
        if all(str(i) in periods for i in range(1, 49))
    )
    if not complete:
        raise ValueError("No complete day found")

    def summary(day):
        result = {}
        for area, column in AREAS.items():
            values = [
                float(by_day[day][str(i)][column])
                for i in range(1, 49)
            ]
            result[area] = {
                "average": round(sum(values) / 48, 2),
                "maximum": round(max(values), 2),
                "minimum": round(min(values), 2),
            }
        return result

    day = complete[-1]
    current = summary(day)
    previous_day = complete[-2] if len(complete) > 1 else None
    if previous_day:
        previous = summary(previous_day)
        for area in AREAS:
            current[area]["average_change"] = round(
                current[area]["average"] - previous[area]["average"], 2
            )

    now = datetime.now(timezone(timedelta(hours=9))).isoformat()
    output = {
        "source": URL,
        "retrieved_at": now,
        "date": day,
        "previous_date": previous_day,
        "unit": "JPY/kWh",
        "prices": current,
    }

    Path("data").mkdir(exist_ok=True)
    Path("data/daily_summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    Path("data/latest.json").write_text(
        json.dumps({
            "source": URL,
            "retrieved_at": now,
            "row_count": len(rows),
            "columns": list(rows[0].keys()),
            "latest_row": rows[-1],
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
