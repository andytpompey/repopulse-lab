import os
import json
import csv
from datetime import datetime, timedelta, timezone
import requests

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PRED_DIR = os.path.join(REPO_ROOT, "predictions")
DATA_DIR = os.path.join(REPO_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

GH_TOKEN = os.environ.get("GH_TOKEN")
HEADERS = {"Accept": "application/vnd.github+json"}
if GH_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GH_TOKEN}"

OUTCOMES_CSV = os.path.join(DATA_DIR, "outcomes.csv")

def gh_get(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def brier(p, y):
    return (p - y) ** 2

def main():
    now = datetime.now(timezone.utc)
    target_date = (now - timedelta(days=7)).date().isoformat()
    pred_path = os.path.join(PRED_DIR, f"predictions_{target_date}.json")

    if not os.path.exists(pred_path):
        print(f"No predictions file for {target_date}, nothing to score.")
        return

    with open(pred_path, "r", encoding="utf-8") as f:
        preds = json.load(f)

    rows = []
    brier_scores = []
    abs_errors = []

    for p in preds:
        full_name = p["full_name"]
        repo = gh_get(f"https://api.github.com/repos/{full_name}")
        stars_then = int(repo.get("stargazers_count", 0))

        stars_at_pred = int(p["stars_now"])
        delta = stars_then - stars_at_pred
        threshold = int(p["breakout_threshold_7d"])
        y = 1 if delta >= threshold else 0

        prob = float(p["p_breakout_7d"])
        bs = brier(prob, y)
        brier_scores.append(bs)

        stars_pred = int(p["stars_pred_7d"])
        ae = abs(stars_then - stars_pred)
        abs_errors.append(ae)

        rows.append({
            "prediction_date_utc": target_date,
            "scored_date_utc": now.date().isoformat(),
            "full_name": full_name,
            "html_url": p["html_url"],
            "stars_at_prediction": stars_at_pred,
            "stars_after_7d": stars_then,
            "delta_stars": delta,
            "breakout_threshold": threshold,
            "breakout_actual": y,
            "p_breakout_7d": prob,
            "brier_score": round(bs, 6),
            "stars_pred_7d": stars_pred,
            "abs_error_stars": ae,
            "model": p.get("model", {}).get("type", "unknown"),
        })

    mean_brier = sum(brier_scores) / max(1, len(brier_scores))
    mean_mae = sum(abs_errors) / max(1, len(abs_errors))

    file_exists = os.path.exists(OUTCOMES_CSV)
    with open(OUTCOMES_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    summary = {
        "prediction_date_utc": target_date,
        "scored_date_utc": now.date().isoformat(),
        "n": len(rows),
        "mean_brier": round(mean_brier, 6),
        "mean_mae_stars": round(mean_mae, 3),
    }
    summary_path = os.path.join(DATA_DIR, f"summary_{target_date}.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Scored {len(rows)} repos from {target_date}")
    print(f"Mean Brier: {mean_brier:.4f} | Mean MAE(stars): {mean_mae:.1f}")
    print(f"Appended to: {OUTCOMES_CSV}")
    print(f"Wrote: {summary_path}")

if __name__ == "__main__":
    main()
