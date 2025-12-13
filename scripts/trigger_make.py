import os
import json
from datetime import datetime, timezone
import requests

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
POSTS_DIR = os.path.join(REPO_ROOT, "posts")

MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL")

def main():
    if not MAKE_WEBHOOK_URL:
        raise RuntimeError("MAKE_WEBHOOK_URL is not set")

    today = datetime.now(timezone.utc).date().isoformat()
    post_path = os.path.join(POSTS_DIR, f"post_{today}.json")
    if not os.path.exists(post_path):
        raise FileNotFoundError(f"Post file not found: {post_path}")

    with open(post_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    r = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=30)
    r.raise_for_status()
    print(f"Triggered Make for {payload.get('post_id')}")

if __name__ == "__main__":
    main()
