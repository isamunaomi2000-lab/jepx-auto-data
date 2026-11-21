import csv
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
today = datetime.now(JST).date()

BASE = Path("data/predictions")
TEPCO = Path("data/predictions_tepco")
ACTUAL = Path("data/jepx/history")
OUTPUT = Path("data/evaluation")
OUTPUT.mkdir(parents=True, exist_ok=True)


def read_prices(path, column):
    if not path.exists():
        return None

    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))

        prices = {
            int(row["period"]): float(row[column])
            for row in rows
        }

        if set(prices) != set(range(1, 49)):
            return None

        return prices
    except (KeyError, ValueError, OSError):
        return None


def accuracy(predicted, actual):
    errors = [
        predicted[p] - actual[p]
        for p in range(1, 49)
    ]

    return {
        "mae": round(sum(abs(e) for e in errors) / 48, 3),
        "rmse": round(
            (sum(e * e for e in errors) / 48) ** 0.5, 3
        ),
        "bias": round(sum(errors) / 48, 3),
    }


results = []

for base_file in sorted(BASE.glob("*.csv")):
    date_text = base_file.stem

    try:
        target_date = datetime.strptime(
            date_text, "%Y-%m-%d"
        ).date()
    except ValueError:
        continue

    if target_date >= today:
        continue

    actual = read_prices(
        ACTUAL / base_file.name,
        "tokyo_yen_kwh"
    )
    base = read_prices(
        base_file,
        "predicted_tokyo_yen_kwh"
    )
    tepco = read_prices(
        TEPCO / base_file.name,
        "tepco_adjusted_yen_kwh"
    )

    if actual is None or base is None:
        continue

    base_score = accuracy(base, actual)

    row = {
        "date": date_text,
        "periods": 48,
        "mae_yen_kwh": base_score["mae"],
        "rmse_yen_kwh": base_score["rmse"],
        "bias_yen_kwh": base_score["bias"],
        "tepco_mae_yen_kwh": "",
        "tepco_rmse_yen_kwh": "",
        "tepco_bias_yen_kwh": "",
        "winner": "not_comparable",
    }

    if tepco is not None:
        tepco_score = accuracy(tepco, actual)

        row["tepco_mae_yen_kwh"] = tepco_score["mae"]
        row["tepco_rmse_yen_kwh"] = tepco_score["rmse"]
        row["tepco_bias_yen_kwh"] = tepco_score["bias"]

        if base_score["mae"] < tepco_score["mae"]:
            row["winner"] = "baseline"
        elif tepco_score["mae"] < base_score["mae"]:
            row["winner"] = "tepco"
        else:
            row["winner"] = "tie"

    results.append(row)


fields = [
    "date",
    "periods",
    "mae_yen_kwh",
    "rmse_yen_kwh",
    "bias_yen_kwh",
    "tepco_mae_yen_kwh",
    "tepco_rmse_yen_kwh",
    "tepco_bias_yen_kwh",
    "winner",
]

with (OUTPUT / "daily_accuracy.csv").open(
    "w", encoding="utf-8-sig", newline=""
) as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(results)


compared = [
    r for r in results
    if r["winner"] != "not_comparable"
]

summary = {
    "evaluated_days": len(results),
    "compared_days": len(compared),
    "baseline_wins": sum(
        r["winner"] == "baseline" for r in compared
    ),
    "tepco_wins": sum(
        r["winner"] == "tepco" for r in compared
    ),
    "ties": sum(
        r["winner"] == "tie" for r in compared
    ),
    "average_baseline_mae_yen_kwh": (
        round(
            sum(r["mae_yen_kwh"] for r in compared)
            / len(compared), 3
        )
        if compared else None
    ),
    "average_tepco_mae_yen_kwh": (
        round(
            sum(r["tepco_mae_yen_kwh"] for r in compared)
            / len(compared), 3
        )
        if compared else None
    ),
    "daily_results": results,
}

(OUTPUT / "summary.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print(json.dumps(summary, ensure_ascii=False, indent=2))
