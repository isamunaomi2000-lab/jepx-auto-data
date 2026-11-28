"""Download the public HJKS CSV and select outages overlapping report dates."""
import argparse
import csv
import io
import json
from collections import Counter
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from fetch_jepx import JST

SOURCE = "https://hjks.jepx.or.jp/hjks/outages"
COLUMNS = {
    "area": "エリア", "station_code": "発電所コード", "station": "発電所名",
    "unit": "ユニット名", "capacity_kw": "認可出力", "category": "停止区分",
    "reason_type": "種別", "reduction_kw": "低下量", "starts_at": "停止日時",
    "recovery_outlook": "復旧見通し", "scheduled_recovery": "復旧予定日",
    "updated_at": "最終更新日時",
}


class DownloadForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.action = None
        self.fields = {}
        self.in_form = False

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "form":
            action = attrs.get("action", "")
            self.in_form = attrs.get("method") == "post" and action.split(";")[0] == "outages"
            if self.in_form:
                self.action = action
        elif tag == "input" and self.in_form and attrs.get("name"):
            if attrs.get("type") in {"hidden", "text"}:
                self.fields[attrs["name"]] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.in_form = False


def download():
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    form = DownloadForm()
    with opener.open(SOURCE, timeout=25) as response:
        form.feed(response.read().decode("utf-8"))
    if not form.action or not {"csv", "_csrf"}.issubset(form.fields):
        raise ValueError("HJKS public CSV form is missing expected fields")
    url = urljoin(SOURCE, form.action)
    if urlsplit(url).hostname != urlsplit(SOURCE).hostname:
        raise ValueError("unexpected HJKS CSV download host")
    request = Request(url, data=urlencode({**form.fields, "csv": "csv"}).encode(), headers={"Referer": SOURCE})
    with opener.open(request, timeout=35) as response:
        if response.headers.get_content_type() != "text/csv":
            raise ValueError("HJKS public download did not return a CSV")
        return response.read().decode("cp932")


def calendar_date(value):
    return date.fromisoformat(value.strip()[:10].replace("/", "-"))


def collect(now, content):
    reader = csv.DictReader(io.StringIO(content))
    if not set(COLUMNS.values()).issubset(reader.fieldnames or []):
        raise ValueError("HJKS official CSV has an unexpected header")
    target_days = (now.date(), now.date() + timedelta(days=1))
    days = {day: [] for day in target_days}
    source_rows = 0
    for raw in reader:
        source_rows += 1
        row = {key: raw[column].strip() for key, column in COLUMNS.items()}
        starts = calendar_date(row["starts_at"])
        recovery = calendar_date(row["scheduled_recovery"]) if row["scheduled_recovery"] else None
        for day in target_days:
            if starts > day or (recovery and recovery < day):
                continue
            if starts < day and recovery is None:
                # The source gives no end date. Keep these out of the dated
                # counts because an older record alone does not prove an outage.
                continue
            days[day].append(row)
    if not source_rows:
        raise ValueError("HJKS official CSV returned no records")

    summaries = {}
    for day, entries in days.items():
        by_category = Counter(row["category"] for row in entries)
        priority = sorted(entries, key=lambda row: int(row["reduction_kw"] or row["capacity_kw"] or 0),
                          reverse=True)
        summaries[day.isoformat()] = {
            "matching_records": len(entries),
            "by_category": dict(by_category),
            "largest_disclosed_records": priority[:10],
        }
    return {
        "status": "ok", "source": SOURCE, "retrieved_at": now.isoformat(),
        "source_rows": source_rows,
        "filter": "starts on date or overlaps dated scheduled recovery; undated older records excluded",
        "dates": summaries,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, help="Official CSV downloaded in a browser")
    args = parser.parse_args()
    content = args.csv.read_bytes().decode("cp932") if args.csv else download()
    result = collect(datetime.now(JST), content)
    output = Path("data/hjks/latest.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f'HJKS CSV verified: {result["source_rows"]} source records')
    for day, stats in result["dates"].items():
        print(day, stats["matching_records"], stats["by_category"])
