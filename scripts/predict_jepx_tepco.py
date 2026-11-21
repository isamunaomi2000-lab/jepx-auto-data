import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
target = datetime.now(JST).date() + timedelta(days=1)
date_str = target.isoformat()

base_file = Path("data/predictions") / f"{date_str}.csv"
tepco_file = Path("data/tepco/tomorrow_latest.csv")
output_dir = Path("data/predictions_tepco")
output_dir.mkdir(parents=True, exist_ok=True)

if not base_file.exists():
    raise SystemExit(f"Missing base forecast: {base_file}")

if not tepco_file.exists():
    raise SystemExit(f"Missing TEPCO data: {tepco_file}")

# Read the original JEPX price forecast
with base_file.open(encoding="utf-8-sig", newline="") as f:
    base = {
        int(row["period"]): float(
            row["predicted_tokyo_yen_kwh"]
        )
        for row in csv.DictReader(f)
    }

# Read TEPCO demand and renewable forecasts
raw = tepco_file.read_bytes()
decoded = None

for encoding in ("cp932", "utf-8-sig"):
    try:
        decoded = raw.decode(encoding)
        break
    except UnicodeDecodeError:
        continue

if decoded is None:
    raise SystemExit("Cannot decode TEPCO CSV")

lines = decoded.splitlines()

if len(lines) < 4:
    raise SystemExit("TEPCO CSV is incomplete")

reader = csv.DictReader(io.StringIO("\n".join(lines[2:])))
tepco = {}

for row in reader:
    if row["日付(yyyymmdd)"].strip() != target.strftime("%Y%m%d"):
        continue

    period = int(row["時間コマ(1時～48時)"])

    tepco[period] = {
        "demand": float(
            row["エリア総需要量[30分kWh]"]
        ),
        "generation": float(
            row["エリア総発電量[30分kWh]"]
        ),
        "renewables": float(
            row["エリア風力・太陽光発電量[30分kWh]"]
        ),
    }

if set(base) != set(range(1, 49)):
    raise SystemExit("Base forecast does not have 48 periods")

if set(tepco) != set(range(1, 49)):
    raise SystemExit(
        f"TEPCO forecast has {len(tepco)} periods, expected 48"
    )

avg_demand = sum(
    row["demand"] for row in tepco.values()
) / 48

avg_renewables = sum(
    row["renewables"] for row in tepco.values()
) / 48

# Experimental coefficients, not yet trained
DEMAND_WEIGHT = 0.10
RENEWABLE_WEIGHT = 0.05

output_file = output_dir / f"{date_str}.csv"

with output_file.open(
    "w", encoding="utf-8-sig", newline=""
) as f:
    writer = csv.writer(f)

    writer.writerow([
        "target_date",
        "period",
        "baseline_yen_kwh",
        "tepco_adjusted_yen_kwh",
        "demand_30min_kwh",
        "generation_30min_kwh",
        "wind_solar_30min_kwh",
        "method",
    ])

    for period in range(1, 49):
        baseline = base[period]
        data = tepco[period]

        demand_ratio = (
            data["demand"] / avg_demand - 1
            if avg_demand > 0 else 0
        )

        renewable_ratio = (
            data["renewables"] / avg_renewables - 1
            if avg_renewables > 0 else 0
        )

        adjustment = (
            DEMAND_WEIGHT * demand_ratio
            - RENEWABLE_WEIGHT * renewable_ratio
        )

        prediction = max(
            0, baseline * (1 + adjustment)
        )

        writer.writerow([
            date_str,
            period,
            round(baseline, 2),
            round(prediction, 2),
            data["demand"],
            data["generation"],
            data["renewables"],
            "tepco_trial_relative_adjustment",
        ])

print(f"Saved: {output_file}")
print("Forecast periods: 48")
print("TEPCO trial prediction completed")
