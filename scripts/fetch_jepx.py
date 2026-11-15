
import csv
import io
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

URL = "https://japanesepower.org/jepxSpot.csv"

def main():
    request = urllib.request.Request(
        URL, headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()

    text = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))

    if not rows:
        raise ValueError("CSVにデータがありません")

    output = {
        "source": URL,
        "retrieved_at": datetime.now(
            timezone(timedelta(hours=9))
        ).isoformat(),
        "row_count": len(rows),
        "columns": list(rows[0].keys()),
        "latest_row": rows[-1],
    }

    Path("data").mkdir(exist_ok=True)
    Path("data/latest.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
