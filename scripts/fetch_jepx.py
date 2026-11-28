"""Read JEPX's official fiscal-year spot CSV and publish verified daily prices."""
import csv
import io
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
SPOT_PAGE = "https://www.jepx.jp/electricpower/market-data/spot/"
CSV_URL = "https://www.jepx.jp/js/csv_read.php?dir=spot_summary&file=spot_summary_{}.csv"
COLUMNS = {
    "system": "システムプライス(円/kWh)",
    "tokyo": "エリアプライス東京(円/kWh)",
    "kansai": "エリアプライス関西(円/kWh)",
    "kyushu": "エリアプライス九州(円/kWh)",
    "buy": "買い入札量(kWh)",
    "sell": "売り入札量(kWh)",
    "contracted": "約定総量(kWh)",
}
LATEST_COLUMNS = {
    "System Price Yen/kWh": COLUMNS["system"],
    **{
        f"{area} Yen/kWh": f"エリアプライス{label}(円/kWh)"
        for area, label in (
            ("Hokkaido", "北海道"), ("Tohoku", "東北"), ("Tokyo", "東京"), ("Chuubu", "中部"),
            ("Hokuriku", "北陸"), ("Kansai", "関西"), ("Chuugoku", "中国"),
            ("Kyushu", "九州"), ("Shikoku", "四国"),
        )
    },
    "Sell Bid Volume kWh": COLUMNS["sell"],
    "Buy Bid Volume kWh": COLUMNS["buy"],
    "Contracted Total Volume kWh": COLUMNS["contracted"],
    "Sell Block Bid Total Volume kWh": "売りブロック入札総量(kWh)",
    "Sell Block Contracted Total Volume kWh": "売りブロック約定総量(kWh)",
    "Buy Block Bid Total Volume kWh": "買いブロック入札総量(kWh)",
    "Buy Block Contracted Total Volume kWh": "買いブロック約定総量(kWh)",
}
PERIODS = set(range(1, 49))


def fiscal_year(day):
    return day.year - (day.month < 4)


def load_days(start, end):
    days = defaultdict(dict)
    sources = {}
    raw_days = defaultdict(dict)
    source_row_count = 0
    for year in range(fiscal_year(start), fiscal_year(end) + 1):
        url = CSV_URL.format(year)
        request = Request(url, headers={"Referer": SPOT_PAGE, "Cache-Control": "no-cache"})
        with urlopen(request, timeout=30) as response:
            raw = response.read()
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw.decode("cp932")
        reader = csv.DictReader(io.StringIO(content))
        required = {"受渡日", "時刻コード", *COLUMNS.values()}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"JEPX CSV has an unexpected header: {url}")
        for row in reader:
            source_row_count += 1
            day = date.fromisoformat(row["受渡日"].strip().replace("/", "-"))
            if not start <= day <= end:
                continue
            period = int(row["時刻コード"])
            if period not in PERIODS or period in days[day]:
                raise ValueError(f"JEPX invalid or duplicate period: {day} / {period}")
            values = {key: Decimal(row[column]) for key, column in COLUMNS.items()}
            if not all(value.is_finite() for value in values.values()):
                raise ValueError(f"JEPX nonfinite numeric field: {day} / {period}")
            days[day][period] = values
            raw_days[day][period] = row
            sources[day] = url
    complete_days = {day: rows for day, rows in days.items() if rows.keys() == PERIODS}
    return complete_days, sources, raw_days, source_row_count


def price_stats(rows, area):
    values = [row[area] for row in rows.values()]
    return {
        "average": round(float(sum(values) / 48), 2),
        "maximum": float(max(values)),
        "minimum": float(min(values)),
    }


def publish(now):
    today = now.date()
    days, sources, raw_days, row_count = load_days(today - timedelta(days=6), today)
    if today not in days:
        raise ValueError(f"JEPX official CSV does not contain all 48 periods for {today}")

    def summary(day):
        rows = days[day]
        previous_day = day - timedelta(days=1)
        prices = {}
        for area in ("system", "tokyo", "kansai", "kyushu"):
            stats = price_stats(rows, area)
            if previous_day in days:
                previous = price_stats(days[previous_day], area)
                stats["average_change"] = round(stats["average"] - previous["average"], 2)
            prices[area] = stats
        return {
            "source": sources[day],
            "retrieved_at": now.isoformat(),
            "date": day.isoformat(),
            "previous_date": previous_day.isoformat() if previous_day in days else None,
            "unit": "JPY/kWh",
            "period_count": len(rows),
            "contracted_total_kwh": int(sum(row["contracted"] for row in rows.values())),
            "prices": prices,
        }

    daily = summary(today)
    output = Path("data")
    output.mkdir(exist_ok=True)
    (output / "daily_summary.json").write_text(
        json.dumps(daily, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    last_row = {
        "datetime": f"{today} 23:30:00", "Date": today.isoformat(), "PeriodID": "48",
        **{key: raw_days[today][48].get(column) for key, column in LATEST_COLUMNS.items()},
    }
    latest = {
        "source": sources[today], "retrieved_at": now.isoformat(),
        "row_count": row_count, "columns": list(last_row), "latest_row": last_row,
    }
    (output / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return daily


if __name__ == "__main__":
    print(json.dumps(publish(datetime.now(JST)), ensure_ascii=False, indent=2))
