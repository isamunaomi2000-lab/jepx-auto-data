import csv
import io
from pathlib import Path

JEPX_DIR = Path("data/jepx/history")
TEPCO_DIR = Path("data/tepco")
OUTPUT_DIR = Path("data/analysis")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def read_csv(path):
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Cannot decode {path}")

def load_tepco(path):
    lines = read_csv(path).splitlines()
    if len(lines) < 4:
        raise ValueError(f"Invalid TEPCO CSV: {path}")
    rows = csv.DictReader(io.StringIO("\n".join(lines[2:])))
    result = {}
    for row in rows:
        day = row["日付(yyyymmdd)"].strip()
        period = int(row["時間コマ(1時～48時)"])
        result[(day, period)] = row
    return result

tepco = {}
for path in sorted((TEPCO_DIR / "history").glob("*.csv")):
    try:
        tepco.update(load_tepco(path))
    except (ValueError, KeyError):
        print(f"Skipping {path}")

for name in ("today_latest.csv", "tomorrow_latest.csv"):
    path = TEPCO_DIR / name
    if path.exists():
        tepco.update(load_tepco(path))

fields = [
    "date", "period", "tokyo_yen_kwh",
    "system_yen_kwh", "demand_30min_kwh",
    "generation_30min_kwh", "wind_solar_30min_kwh"
]

matched = []
for path in sorted(JEPX_DIR.glob("*.csv")):
    for row in csv.DictReader(io.StringIO(read_csv(path))):
        date = row["date"]
        period = int(row["period"])
        day = date.replace("-", "")
        forecast = tepco.get((day, period))
        if forecast is None:
            continue
        matched.append({
            "date": date,
            "period": period,
            "tokyo_yen_kwh": row["tokyo_yen_kwh"],
            "system_yen_kwh": row["system_yen_kwh"],
            "demand_30min_kwh": forecast["エリア総需要量[30分kWh]"],
            "generation_30min_kwh": forecast["エリア総発電量[30分kWh]"],
            "wind_solar_30min_kwh": forecast["エリア風力・太陽光発電量[30分kWh]"]
        })

output = OUTPUT_DIR / "jepx_tepco_comparison.csv"
with output.open("w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=fields)
    writer.writeheader()
    writer.writerows(matched)

print(f"Matched {len(matched)} half-hour records")
print(f"Saved {output}")
