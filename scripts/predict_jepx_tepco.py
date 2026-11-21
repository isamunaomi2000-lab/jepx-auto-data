import csv
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).date()
target = today + timedelta(days=1)
date_str = target.isoformat()

BASE = Path("data/predictions") / f"{date_str}.csv"
TEPCO = Path("data/tepco/tomorrow_latest.csv")
OUTPUT_DIR = Path("data/predictions_tepco")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

if not BASE.exists():
    raise SystemExit(f"Base prediction missing: {BASE}")
if not TEPCO.exists():
    raise SystemExit(f"TEPCO forecast missing: {TEPCO}")

with BASE.open(encoding="utf-8-sig", newline="") as f:
    base = {
        int(row["period"]): row
        for row in csv.DictReader(f)
    }

raw = TEPCO.read_bytes()
decoded = None
for encoding in ("cp932", "utf-8-sig"):
    try:
        decoded = raw.decode(encoding)
        break
    except UnicodeDecodeError:
        pass

if decoded is None:
    raise SystemExit("Cannot decode TEPCO forecast")

lines = decoded.splitlines()
if len(lines) < 4:
    raise SystemExit("Invalid TEPCO CSV")

tepco = {}
reader = csv.DictReader(io.StringIO("\n".join(lines[2:])))

for row in reader:
    row_date = row["日付(yyyymmdd)"].strip()
    if row_date != target.strftime("%Y%m%d"):
        continue

    period = int(row["時間コマ(1時～48時)"])
    tepco[period] = {
        "demand": float(row["エリア総需要量[30分kWh]"]),
        "generation": float(row["エリア総発電量[30分kWh]"]),
        "renewables": float(
            row["エリア風力・太陽光発電量[30分kWh]"
        ),
    }

if len(base) != 48 or len(tepco) != 48:
    raise SystemExit(
        f"Expected 48 periods: base={len(base)}, tepco={len(tepco)}"
    )

avg_demand = sum(
    row["demand"] for row in tepco.values()
) / 48

avg_renewables = sum(
    row["renewables"] for row in tepco.values()
) / 48

# Trial model: small adjustment relative to daily average.
# These coefficients are provisional, not statistically trained.
DEMAND_WEIGHT = 0.10
RENEWABLE_WEIGHT = 0.05

output = OUTPUT_DIR / f"{date_str}.csv"

with output.open("w", encoding="utf-8-sig", newline="") as f:
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
        baseline = float(
            base[period]["predicted_tokyo_yen_kwh"]
        )
        data = tepco[period]

        demand_ratio = (
            data["demand"] / avg_demand - 1
            if avg_demand else 0
        )
        renewable_ratio = (
            data["renewables"] / avg_renewables - 1
            if avg_renewables else 0
        )

        adjustment = (
            DEMAND_WEIGHT * demand_ratio
            - RENEWABLE_WEIGHT * renewable_ratio
        )

        predicted = max(0, baseline * (1 + adjustment))

        writer.writerow([
            date_str,
            period,
            round(baseline, 2),
            round(predicted, 2),
            data["demand"],
            data["generation"],
            data["renewables"],
            "tepco_trial_relative_adjustment",
        ])

print(f"Saved: {output}")
print("Forecast periods: 48")
print("Model: experimental TEPCO adjustment")
