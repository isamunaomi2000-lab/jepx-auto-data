"""Download TEPCO Power Grid area demand forecast CSV files."""
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import csv
import io
import json

BASE = "https://www4.tepco.co.jp/forecast/html/images/"
SOURCES = {
    "today": "AREA_YOSOKU.csv",
    "tomorrow": "AREA_ONCE_YOSOKU.csv",
}
OUTPUT = Path("data/tepco")
OUTPUT.mkdir(parents=True, exist_ok=True)

now = datetime.now(ZoneInfo("Asia/Tokyo"))
results = {}

for label, filename in SOURCES.items():
    url = BASE + filename
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=30) as response:
            raw = response.read()
        if not raw:
            raise ValueError("Empty CSV")
        decoded = None
        for encoding in ("utf-8-sig", "cp932"):
            try:
                decoded = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("Unsupported CSV encoding")
        rows = list(csv.reader(io.StringIO(decoded)))
        if len(rows) < 2:
            raise ValueError("CSV contains too few rows")
        (OUTPUT / (label + "_latest.csv")).write_bytes(raw)
        results[label] = {
            "status": "ok",
            "source": url,
            "rows": len(rows),
            "downloaded_at_jst": now.isoformat(),
        }
        print(f"{label}: downloaded {len(raw)} bytes")
    except Exception as exc:
        results[label] = {"status": "error", "source": url, "error": str(exc)}
        print(f"{label}: ERROR: {exc}")

(OUTPUT / "download_status.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
if any(item["status"] == "error" for item in results.values()):
    raise SystemExit(1)

# Save dated snapshots for historical analysis
HISTORY = OUTPUT / "history"
HISTORY.mkdir(parents=True, exist_ok=True)

for label in SOURCES:
    if results[label]["status"] != "ok":
        continue
    latest = OUTPUT / (label + "_latest.csv")
    with latest.open("r", encoding="cp932") as file:
        metadata = list(csv.reader(file))[:2]
    target_date = metadata[1][2]
    if not (len(target_date) == 8 and target_date.isdigit()):
        raise ValueError("Invalid forecast target date")
    snapshot = HISTORY / f"{target_date}_{label}_{now.strftime('%Y%m%d_%H%M%S')}.csv"
    snapshot.write_bytes(latest.read_bytes())
    print(f"Saved historical snapshot: {snapshot}")
