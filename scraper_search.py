# scraper_search.py
# Search Bluesky posts by keywords -> expand using get_data.py -> save as CSV

import os
import csv
import time
from pathlib import Path
from typing import List, Dict, Any

import requests
from dotenv import load_dotenv
from get_data import get_post_as_csv_row_http, API_BASE

load_dotenv(override=True)

# Credentials from .env
HANDLE = os.getenv("USERNAME")
APP_PASSWORD = os.getenv("PW")

# Path to CSV containing search queries
QUERIES_CSV = Path("labeler_inputs/coercion_queries.csv")

# How many posts to fetch per query
POSTS_PER_QUERY = 18

# Output file
OUTPUT_CSV = "posts_data_raw.csv"


def login(handle: str, app_password: str) -> str:
    """Login once and return JWT access token."""
    res = requests.post(
        f"{API_BASE}/com.atproto.server.createSession",
        json={"identifier": handle, "password": app_password},
        timeout=10,
    )
    res.raise_for_status()
    return res.json()["accessJwt"]


def load_queries_from_csv() -> List[str]:
    """
    Load keyword queries from coercion_queries.csv.
    Only the 'query' column is used.
    """
    if not QUERIES_CSV.exists():
        raise FileNotFoundError(f"{QUERIES_CSV} not found. Please create the file.")

    queries: List[str] = []
    with QUERIES_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = (row.get("query") or "").strip()
            if q:
                queries.append(q)

    if not queries:
        raise RuntimeError(f"No valid queries found in {QUERIES_CSV}")

    return queries


def search_posts(query: str, headers: Dict[str, str], limit: int = 25) -> List[Dict[str, Any]]:
    """
    Use app.bsky.feed.searchPosts to retrieve posts for a given keyword.
    Requires authorization headers.
    """
    url = f"{API_BASE}/app.bsky.feed.searchPosts"
    params = {"q": query, "limit": limit}

    r = requests.get(url, headers=headers, params=params, timeout=15)
    if r.status_code != 200:
        print(f"[WARN] searchPosts({query}) -> {r.status_code}")
        return []

    data = r.json()
    return data.get("posts", [])


def main():
    if not HANDLE or not APP_PASSWORD:
        raise RuntimeError("USERNAME / PW not configured in .env")

    # Login once and reuse token for searchPosts
    token = login(HANDLE, APP_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    search_queries = load_queries_from_csv()
    print(f"[INFO] Loaded {len(search_queries)} queries from {QUERIES_CSV}")

    seen_uris = set()
    rows: List[Dict[str, Any]] = []

    # Loop through each search query
    for q in search_queries:
        print(f"\n[SEARCH] query = {q}")
        posts = search_posts(q, headers=headers, limit=POSTS_PER_QUERY)
        print(f"[SEARCH] Found {len(posts)} posts")

        for p in posts:
            uri = p.get("uri")
            if not uri or uri in seen_uris:
                continue
            seen_uris.add(uri)

            try:
                print(f"[FETCH] {uri}")
                row = get_post_as_csv_row_http(uri, token=token)
                rows.append(row)
                time.sleep(0.2)  # avoid rate limit
            except Exception as e:
                print(f"[ERROR] Failed to fetch {uri}: {e}")

    if not rows:
        print("[DONE] No posts fetched.")
        return

    # Write results to CSV
    # Some rows may have extra fields (e.g., different embed_* combinations),
    # so compute the union of all keys across rows.
    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())
    fieldnames = sorted(all_keys)

    print(f"\n[WRITE] Writing {len(rows)} rows -> {OUTPUT_CSV}")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print("[DONE] Scraper finished.")


if __name__ == "__main__":
    main()