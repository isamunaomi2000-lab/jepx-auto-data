import csv
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

PREDICTIONS = Path("data/predictions")
HISTORY = Path("data/jepx/history")
OUTPUT = Path("data/evaluation")
OUTPUT.mkdir(parents=True, exist_ok=True)

jst = timezone(timedelta(hours=9))
today = datetime.now(jst).date()

results = []

for prediction_file in sorted(PREDICTIONS.glob("*.csv")):
    date_text = prediction_file.stem
    try:
        target_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        continue

    # Future dates must not be evaluated.
    if target_date >= today:
        continue

    actual_file = HISTORY / prediction_file.name
    if not actual_file.exists():
        continue

    with prediction_file.open(encoding="utf-8-sig", newline="") as f:
        predictions = {
            int(row["period"]): float(row["predicted_tokyo_yen_kwh"])
            for row in csv.DictReader(f)
        }

    with actual_file.open(encoding="utf-8-sig", newline="") as f:
        actuals = {
            int(row["period"]): float(row["tokyo_yen_kwh"])
            for row in csv.DictReader(f)
        }

    # Evaluate only when all 48 periods are available.
    periods = range(1, 49)
    if not all(p in predictions and p in actuals for p in periods):
        continue

    errors = [predictions[p] - actuals[p] for p in periods]
    mae = sum(abs(e) for e in errors) / 48
    rmse = (sum(e * e for e in errors) / 48) ** 0.5
    bias = sum(errors) / 48

    results.append({
        "date": date_text,
        "periods": 48,
        "mae_yen_kwh": round(mae, 3),
        "rmse_yen_kwh": round(rmse, 3),
        "bias_yen_kwh": round(bias, 3)
    })

fields = [
    "date", "periods", "mae_yen_kwh",
    "rmse_yen_kwh", "bias_yen_kwh"
]

with (OUTPUT / "daily_accuracy.csv").open(
    "w", encoding="utf-8-sig", newline=""
) as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(results)

summary = {
    "evaluated_days": len(results),
    "average_daily_mae_yen_kwh": (
        round(sum(r["mae_yen_kwh"] for r in results) / len(results), 3)
        if results else None
    ),
    "daily_results": results
}

(OUTPUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(json.dumps(summary, ensure_ascii=False, indent=2))
