"""Collect TEPCO PG forecasts, yesterday's actuals and Tokyo supply peaks."""
import csv
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from fetch_jepx import JST, PERIODS

BASE = "https://www4.tepco.co.jp/forecast/html/images/"
SOURCES = {"today": "AREA_YOSOKU.csv", "tomorrow": "AREA_ONCE_YOSOKU.csv"}
OUTPUT = Path("data/tepco")
DOWNLOAD_PAGE = "https://www.tepco.co.jp/forecast/html/area-download-j.html"


def download(filename):
    headers = {"Referer": DOWNLOAD_PAGE}
    if not filename.endswith(".zip"):
        headers["Cache-Control"] = "no-cache"
    url = BASE + filename
    try:
        with urlopen(Request(url, headers=headers), timeout=25) as response:
            return response.read(), response.url
    except HTTPError as error:
        if not filename.endswith(".zip") or error.code not in (403, 404):
            raise
    # The operator serves the monthly archives on both official hostnames.
    alternate = url.replace("https://www4.tepco.co.jp/", "https://www.tepco.co.jp/", 1)
    with urlopen(Request(alternate, headers=headers), timeout=25) as response:
        return response.read(), response.url


def rows_from_csv(raw):
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp932")
    return list(csv.reader(io.StringIO(content)))


def summarize_area(raw, target, forecast):
    rows = rows_from_csv(raw)
    compact = target.strftime("%Y%m%d")
    if len(rows) < 3 or "対象年月日" not in ",".join(rows[0]):
        raise ValueError("unexpected TEPCO area CSV header")
    if rows[2][4:7] not in (
        ["エリア総需要量", "エリア総発電量", "エリア風力・太陽光発電量"],
        ["エリア総需要量[30分kWh]", "エリア総発電量[30分kWh]", "エリア風力・太陽光発電量[30分kWh]"],
    ):
        raise ValueError("unexpected TEPCO area CSV data columns")
    if not rows[3:] and forecast:
        return {"status": "not_published", "published_metadata_date": rows[1][2], "period_count": 0}
    if rows[1][2] != compact or any(row[0] != compact for row in rows[3:]):
        raise ValueError(f"TEPCO CSV target differs from {target}")
    if len(rows[3:]) != 48 or {int(row[1]) for row in rows[3:]} != PERIODS:
        raise ValueError(f"TEPCO CSV requires 48 distinct periods for {target}")
    entries = [(int(row[1]), *(int(value) for value in row[4:7])) for row in rows[3:]]
    if any(demand <= 0 or generation < 0 or renewables < 0 for _, demand, generation, renewables in entries):
        raise ValueError(f"TEPCO CSV has invalid or unfinished data for {target}")
    period, demand, _, _ = max(entries, key=lambda row: row[1])
    return {
        "status": "ok", "period_count": 48, "peak_demand_period": period,
        "peak_demand_30min_kwh": demand,
        "peak_generation_30min_kwh": max(row[2] for row in entries),
        "peak_wind_solar_30min_kwh": max(row[3] for row in entries),
    }


def summarize_supply(now):
    filename = "juyo-s1-j.csv"
    raw, source = download(filename)
    rows = rows_from_csv(raw)
    updated = datetime.strptime(rows[0][0], "%Y/%m/%d %H:%M UPDATE").replace(tzinfo=JST)
    if updated.date() != now.date():
        raise ValueError(f"TEPCO supply CSV is dated {updated.date()}")
    sections = {
        "today": ("ピーク時供給力(万kW)", "予想最大電力(万kW)", "使用率ピーク時供給力(万kW)"),
        "tomorrow": ("翌日のピーク時供給力(万kW)", "翌日の予想最大電力(万kW)", "翌日の使用率ピーク時供給力(万kW)"),
    }
    values = {
        row[0]: rows[i + 1] for i, row in enumerate(rows[:-1])
        if row and any(row[0] in fields for fields in sections.values())
    }
    summary = {"source": source, "published_at": updated.isoformat()}
    for offset, (label, (supply, demand, utilization)) in enumerate(sections.items()):
        item = {"date": (now.date() + timedelta(days=offset)).isoformat()}
        if label == "tomorrow" and all(not any(values.get(field, [])) for field in sections[label]):
            summary[label] = {**item, "status": "not_published"}
            continue
        summary[label] = {
            **item, "status": "ok", "demand_peak_mw": int(values[demand][0]) * 10,
            "supply_at_demand_peak_mw": int(values[supply][0]) * 10,
            "demand_peak_time": values[demand][1],
            "usage_peak_percent": float(values[utilization][-1]),
            "usage_peak_time": values[utilization][1],
        }
    return summary


def summarize_supply_actual(raw, target):
    rows = rows_from_csv(raw)
    if not rows or rows[0][0] != "単位[MW平均]":
        raise ValueError("unexpected TEPCO area supply and demand CSV unit")
    header = rows[1]
    required = {"DATE", "TIME", "エリア需要", "太陽光発電実績", "風力発電実績", "合計"}
    if not required.issubset(header):
        raise ValueError("unexpected TEPCO area supply and demand CSV header")
    entries = {}
    for values in rows[2:]:
        row = dict(zip(header, values))
        day = datetime.strptime(row["DATE"], "%Y/%m/%d").date()
        if day != target:
            continue
        hour, minute = map(int, row["TIME"].split(":"))
        period = hour * 2 + minute // 30 + 1
        if minute not in (0, 30) or not 0 <= hour < 24 or period in entries:
            raise ValueError(f"invalid TEPCO actual period for {target}: {row['TIME']}")
        demand = int(row["エリア需要"])
        supply = int(row["合計"])
        renewables = int(row["太陽光発電実績"]) + int(row["風力発電実績"])
        if demand <= 0 or supply <= 0 or renewables < 0:
            raise ValueError(f"invalid TEPCO actual quantities for {target}: {row['TIME']}")
        entries[period] = (demand, supply, renewables)
    if entries.keys() != PERIODS:
        raise ValueError(f"TEPCO monthly actual CSV requires 48 periods for {target}")
    period = max(entries, key=lambda period: entries[period][0])
    return {
        "status": "ok", "period_count": 48, "peak_demand_period": period,
        "peak_demand_30min_kwh": entries[period][0] * 500,
        "peak_supply_actual_30min_kwh": max(row[1] for row in entries.values()) * 500,
        "peak_wind_solar_30min_kwh": max(row[2] for row in entries.values()) * 500,
    }


def collect_actual(target, now):
    # This is TEPCO PG's monthly 30-minute area balance CSV, published separately
    # from the area forecast archive. The total includes interconnector flows.
    url = f"https://www.tepco.co.jp/forecast/html/images/eria_jukyu_{target:%Y%m}_03.csv"
    request = Request(url, headers={"Referer": "https://www.tepco.co.jp/forecast/html/area_jukyu-j.html"})
    actual = {"source": url, "date": target.isoformat(), "downloaded_at_jst": now.isoformat()}
    try:
        with urlopen(request, timeout=25) as response:
            return {**actual, "source": response.url, **summarize_supply_actual(response.read(), target)}
    except (OSError, ValueError, KeyError) as error:
        archive_error = str(error)

    filename = f"AREA_{target:%Y%m}.zip"
    member = f"AREA_JISEKI_{target:%Y%m%d}.csv"
    try:
        raw, source = download(filename)
        with ZipFile(io.BytesIO(raw), metadata_encoding="cp932") as archive:
            return {**actual, "source": source, "archive_member": member,
                    **summarize_area(archive.read(member), target, forecast=False)}
    except Exception as error:
        return {**actual, "status": "error", "error": f"monthly CSV: {archive_error}; archive: {error}"}


def collect(now):
    history = OUTPUT / "history"
    history.mkdir(parents=True, exist_ok=True)
    results = {}
    for offset, (label, filename) in enumerate(SOURCES.items()):
        target = now.date() + timedelta(days=offset)
        details = {"source": BASE + filename, "date": target.isoformat(), "downloaded_at_jst": now.isoformat()}
        try:
            raw, details["source"] = download(filename)
            details.update(summarize_area(raw, target, forecast=True))
            if details["status"] == "ok":
                timestamp = now.strftime("%Y%m%d_%H%M%S")
                (OUTPUT / f"{label}_latest.csv").write_bytes(raw)
                (history / f"{target:%Y%m%d}_{label}_{timestamp}.csv").write_bytes(raw)
        except Exception as error:
            details.update(status="error", error=str(error))
        results[label] = details

    target = now.date() - timedelta(days=1)
    results["yesterday_actual"] = collect_actual(target, now)
    try:
        results["supply"] = summarize_supply(now)
    except Exception as error:
        results["supply"] = {"source": BASE + "juyo-s1-j.csv", "status": "error", "error": str(error)}

    (OUTPUT / "download_status.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return results


if __name__ == "__main__":
    results = collect(datetime.now(JST))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(item.get("status") == "error" for item in results.values()):
        raise SystemExit(1)
