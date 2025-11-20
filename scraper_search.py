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
QUERIES_CSV = Path("labeler_inputs/queries_v1.csv")

# How many posts to fetch per query
POSTS_PER_QUERY = 7

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
    Load keyword queries from queries_v1.csv.
    Only the 'phrase' column is used as the search keyword.
    """
    if not QUERIES_CSV.exists():
        raise FileNotFoundError(f"{QUERIES_CSV} not found. Please create the file.")

    queries: List[str] = []
    with QUERIES_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = (row.get("phrase") or "").strip()
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


def uri_to_web_link(uri: str) -> str:
    """Convert an at:// URI into a https://bsky.app/... link for debugging/CSV."""
    if not uri or not isinstance(uri, str):
        return ""
    if not uri.startswith("at://"):
        return ""
    try:
        # at://did:plc:abc/app.bsky.feed.post/3xyz
        _, did, collection, rkey = uri.split("/", 3)
    except ValueError:
        return ""

    if collection == "app.bsky.feed.post":
        return f"https://bsky.app/profile/{did}/post/{rkey}"
    # Fallback for other collections: just profile link
    return f"https://bsky.app/profile/{did}"


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
                print(f"[COLLECT] {uri}")
                record = p.get("record", {})
                author = p.get("author", {})
                row = {
                    "uri": uri,
                    "cid": p.get("cid", ""),
                    "author_did": author.get("did", ""),
                    "author_handle": author.get("handle", ""),
                    # prefer createdAt from the record, fall back to indexedAt from search
                    "created_at": record.get("createdAt", p.get("indexedAt", "")),
                    "text": record.get("text", ""),
                }
                rows.append(row)
            except Exception as e:
                print(f"[ERROR] Failed to collect data for {uri}: {e}")

    if not rows:
        print("[DONE] No posts fetched.")
        return

    # Write results to CSV with a fixed set of columns + link
    # We only keep a small set of useful fields from each row.
    filtered_rows: List[Dict[str, Any]] = []
    for r in rows:
        uri = r.get("uri", "")
        filtered_rows.append(
            {
                "uri": uri,
                "cid": r.get("cid", ""),
                "author_did": r.get("author_did", ""),
                "author_handle": r.get("author_handle", ""),
                # Some helper implementations may use different timestamp keys;
                # prefer created_at, then indexed_at, else empty.
                "created_at": r.get("created_at", r.get("indexed_at", "")),
                "text": r.get("text", ""),
                "link": uri_to_web_link(uri),
            }
        )

    fieldnames = ["uri", "cid", "author_did", "author_handle", "created_at", "text", "link"]

    print(f"\n[WRITE] Writing {len(filtered_rows)} rows -> {OUTPUT_CSV}")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in filtered_rows:
            writer.writerow(r)

    print("[DONE] Scraper finished.")


if __name__ == "__main__":
    main()