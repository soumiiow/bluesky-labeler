#!/usr/bin/env python3
import csv
import json
import sys
import requests
from typing import List, Optional

def uri_to_url(uri: str) -> str:
    """
    Convert a Bluesky at:// URI into a https://bsky.app URL.

    Example
    -------
    at://did:plc:abc123/app.bsky.feed.post/3xyz
    -> https://bsky.app/profile/did:plc:abc123/post/3xyz
    """
    if uri is None:
        return ""
    uri = uri.strip()
    if not uri:
        return ""

    # 已经是 http(s) 的就直接返回
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri

    prefix = "at://"
    if not uri.startswith(prefix):
        # 意外格式，原样返回方便 debug
        return uri

    rest = uri[len(prefix):]
    parts: List[str] = rest.split("/")
    # 预期结构: did, collection(ns id), rkey
    if len(parts) < 3:
        return uri

    did = parts[0]
    rkey = parts[-1]
    return f"https://bsky.app/profile/{did}/post/{rkey}"


def normalize_labels(label_str: str) -> str:
    """
    把逗号分隔的标签字符串变成 JSON list 字符串。

    "sexual violence, trauma discussion"
    -> "["sexual violence", "trauma discussion"]"

    空/缺失 -> "[]"
    """
    if label_str is None:
        return "[]"
    label_str = label_str.strip()
    if not label_str:
        return "[]"

    labels = [s.strip() for s in label_str.split(",") if s.strip()]
    return json.dumps(labels, ensure_ascii=False)


def fetch_thread(uri: str) -> Optional[dict]:
    """
    Call the public Bluesky API to get the post thread for a given at:// URI.
    Returns the parsed JSON dict on success, or None on error.
    """
    if not uri:
        return None

    endpoint = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread"
    try:
        resp = requests.get(endpoint, params={"uri": uri}, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[WARN] failed to fetch thread for {uri}: {e}")
        return None


def _find_post_by_cid(node: dict, target_cid: str) -> Optional[dict]:
    """
    Depth‑first search over a thread node tree to find the post dict
    whose 'cid' matches target_cid.
    """
    if not isinstance(node, dict):
        return None

    post = node.get("post")
    if isinstance(post, dict) and post.get("cid") == target_cid:
        return post

    # Search replies (children)
    for child in node.get("replies", []) or []:
        found = _find_post_by_cid(child, target_cid)
        if found is not None:
            return found

    # Optionally walk up to parent if present
    parent = node.get("parent")
    if parent:
        found = _find_post_by_cid(parent, target_cid)
        if found is not None:
            return found

    return None


def resolve_url_from_cid(uri: str, cid: str) -> str:
    """
    Use the Bluesky thread API plus cid to locate the exact post we care about
    (root or reply) and return its canonical https://bsky.app URL.

    If anything fails, returns an empty string so the caller can fall back to
    simple uri_to_url(uri).
    """
    cid = (cid or "").strip()
    if not cid:
        return ""

    data = fetch_thread(uri)
    if not data or "thread" not in data:
        return ""

    post = _find_post_by_cid(data["thread"], cid)
    if not post:
        return ""

    at_uri = post.get("uri")
    if not at_uri:
        return ""

    return uri_to_url(at_uri)


def transform(input_csv: str, output_csv: str) -> None:
    """
    读 input_csv（至少包含列: uri, Labels，可选列: cid）
    写 output_csv（列名: URL, Labels(JSON list), uri, cid）
    """
    with open(input_csv, newline="", encoding="utf-8") as f_in, \
         open(output_csv, "w", newline="", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        fieldnames = ["URL", "Labels", "uri", "cid"]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            uri = (row.get("uri") or "").strip()
            labels_raw = row.get("Labels")  # 可能为 None
            cid = (row.get("cid") or "").strip()

            # 跳过完全空行
            if not uri:
                continue

            # First get a straightforward URL from the at:// URI
            url = uri_to_url(uri)

            # If we have a cid, try to resolve the exact post (root or reply)
            # via the Bluesky thread API. If resolution fails, keep the
            # straightforward URL.
            resolved = ""
            if cid:
                resolved = resolve_url_from_cid(uri, cid)
            if resolved:
                url = resolved

            labels_json = normalize_labels(labels_raw)
            writer.writerow({
                "URL": url,
                "Labels": labels_json,
                "uri": uri,
                "cid": cid,
            })


def main():
    if len(sys.argv) != 3:
        print("Usage: python transform_uri2url.py input.csv output.csv")
        sys.exit(1)

    input_csv, output_csv = sys.argv[1], sys.argv[2]
    transform(input_csv, output_csv)


if __name__ == "__main__":
    main()