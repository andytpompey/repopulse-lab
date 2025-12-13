import os
import json
import math
from datetime import datetime, timedelta, timezone

import requests

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(REPO_ROOT, "data")
PRED_DIR = os.path.join(REPO_ROOT, "predictions")
POSTS_DIR = os.path.join(REPO_ROOT, "posts")

for d in (DATA_DIR, PRED_DIR, POSTS_DIR):
    os.makedirs(d, exist_ok=True)

GH_TOKEN = os.environ.get("GH_TOKEN")
HEADERS = {"Accept": "application/vnd.github+json"}
if GH_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GH_TOKEN}"


def gh_get(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def logistic(z):
    return 1.0 / (1.0 + math.exp(-z))


def iso_to_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def main():
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()

    created_since = (now - timedelta(days=14)).date().isoformat()
    q = f"created:>={created_since} stars:>=50 archived:false"

    search = gh_get(
        "https://api.github.com/search/repositories",
        params={"q": q, "sort": "stars", "order": "desc", "per_page": 30},
    )

    items = search.get("items", [])
    repos = []
    for it in items:
        full_name = it["full_name"]
        repo = gh_get(f"https://api.github.com/repos/{full_name}")
        repos.append(repo)

    snapshot = []
    predictions = []

    for repo in repos:
        stars_now = int(repo.get("stargazers_count", 0))
        forks_now = int(repo.get("forks_count", 0))
        issues_now = int(repo.get("open_issues_count", 0))
        language = repo.get("language") or "Unknown"

        created_at = iso_to_dt(repo["created_at"])
        pushed_at = iso_to_dt(repo["pushed_at"])
        age_days = max(1.0, (now - created_at).total_seconds() / 86400.0)
        since_push_days = max(0.0, (now - pushed_at).total_seconds() / 86400.0)

        stars_per_day = stars_now / age_days

        z = (
            0.9 * math.log10(stars_per_day + 0.01)
            - 0.25 * since_push_days
            + 0.15 * math.log10(forks_now + 1)
        )
        p_breakout = clamp(logistic(z))

        breakout_threshold = int(max(200, 0.5 * stars_now))

        stars_pred_7d = int(
            round(stars_now + (7 * stars_per_day * (0.8 + 0.6 * p_breakout)))
        )
        band = int(round(max(25, 0.25 * breakout_threshold * (1.0 - p_breakout))))
        low = max(0, stars_pred_7d - band)
        high = stars_pred_7d + band

        snapshot.append(
            {
                "date_utc": today,
                "full_name": repo["full_name"],
                "html_url": repo["html_url"],
                "stars_now": stars_now,
                "forks_now": forks_now,
                "issues_now": issues_now,
                "language": language,
                "created_at": repo["created_at"],
                "pushed_at": repo["pushed_at"],
            }
        )

        predictions.append(
            {
                "date_utc": today,
                "full_name": repo["full_name"],
                "html_url": repo["html_url"],
                "stars_now": stars_now,
                "breakout_threshold_7d": breakout_threshold,
                "p_breakout_7d": round(p_breakout, 4),
                "stars_pred_7d": stars_pred_7d,
                "stars_pred_low_7d": low,
                "stars_pred_high_7d": high,
                "features": {
                    "age_days": round(age_days, 3),
                    "since_push_days": round(since_push_days, 3),
                    "stars_per_day": round(stars_per_day, 3),
                    "forks_now": forks_now,
                    "issues_now": issues_now,
                    "language": language,
                },
                "model": {"type": "heuristic_logistic_v1", "notes": "Reproducible baseline. No LLM."},
            }
        )

    snap_path = os.path.join(DATA_DIR, f"snapshots_{today}.json")
    pred_path = os.path.join(PRED_DIR, f"predictions_{today}.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    with open(pred_path, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2)

    top = sorted(predictions, key=lambda x: x["p_breakout_7d"], reverse=True)[:5]

    lines = []
    lines.append("RepoPulse forecast (7-day breakout watchlist)")
    lines.append("")
    lines.append("Method: reproducible baseline model using public GitHub signals (no LLM).")
    lines.append("Breakout = +max(200 stars, +50%) within 7 days.")
    lines.append("")

    for i, r in enumerate(top, start=1):
        p = int(round(100 * r["p_breakout_7d"]))
        lines.append(
            f"{i}) {r['full_name']} | {p}% | stars now {r['stars_now']} → "
            f"est {r['stars_pred_7d']} "
            f"(range {r['stars_pred_low_7d']}-{r['stars_pred_high_7d']})"
        )
        lines.append(f"   {r['html_url']}")

    lines.append("")
    lines.append(
        "Daily forecasts are logged publicly, then scored 7 days later (hits, misses, calibration)."
    )
    lines.append("#opensource #software #datascience #forecasting #github")

    text = "\n".join(lines).strip()

    post_payload = {"post_id": f"repopulse-{today}", "date_utc": today, "text": text}

    post_path = os.path.join(POSTS_DIR, f"post_{today}.json")
    with open(post_path, "w", encoding="utf-8") as f:
        json.dump(post_payload, f, indent=2)

    print(f"Wrote: {snap_path}")
    print(f"Wrote: {pred_path}")
    print(f"Wrote: {post_path}")


if __name__ == "__main__":
    main()
