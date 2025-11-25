# correct_origianl_url.py
import sys
import csv
import requests

THREAD_ENDPOINT = "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread"


def url_to_uri(url: str) -> str:
    """
    https://bsky.app/profile/<handle_or_did>/post/<rkey>
    -> at://<handle_or_did>/app.bsky.feed.post/<rkey>
    """
    url = url.strip().rstrip("/")
    parts = url.split("/")
    if len(parts) < 5:
        raise ValueError(f"Not a valid Bluesky post URL: {url}")

    handle_or_did = parts[-3]   # profile/<this>/post/<rkey>
    rkey = parts[-1]
    return f"at://{handle_or_did}/app.bsky.feed.post/{rkey}"


def uri_to_url(uri: str) -> str:
    """
    at://<did>/app.bsky.feed.post/<rkey>
    -> https://bsky.app/profile/<did>/post/<rkey>
    （用 did 比 handle 稳定）
    """
    uri = uri.strip()
    parts = uri.split("/")
    if not uri.startswith("at://") or len(parts) < 5:
        raise ValueError(f"Not a valid Bluesky post URI: {uri}")

    did = parts[2]
    rkey = parts[-1]
    return f"https://bsky.app/profile/{did}/post/{rkey}"


def get_root_url_for_post_url(url: str) -> str:
    """
    给一个普通的 post URL：
    - 如果它本身是 root 帖子：返回 ""
    - 如果它是 reply / 引用：返回 root 帖子的 URL
      （查 app.bsky.feed.getPostThread）
    """
    try:
        uri = url_to_uri(url)
    except ValueError:
        # 不符合格式，直接放弃
        print(f"[WARN] skip invalid URL: {url}")
        return ""

    try:
        resp = requests.get(THREAD_ENDPOINT, params={"uri": uri}, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"[WARN] failed to fetch thread for {url}: {e}")
        return ""

    data = resp.json()

    # 可能是 NotFoundPost 之类
    thread = data.get("thread")
    if not isinstance(thread, dict) or "post" not in thread:
        return ""

    post = thread["post"]
    record = post.get("record", {})

    # 没有 reply 字段 → 本来就是 root
    reply_info = record.get("reply")
    if not reply_info:
        return ""

    root = reply_info.get("root") or {}
    root_uri = root.get("uri")
    if not root_uri:
        return ""

    try:
        return uri_to_url(root_uri)
    except ValueError:
        return ""


def main():
    # No extra args: use default paths under this repo
    #   input:  test-data/coercion_gold_all_posts.csv
    #   output: test-data/coercion_gold_all_posts_withroot.csv
    if len(sys.argv) == 1:
        input_csv = "test-data/coercion_gold_all_posts.csv"
        output_csv = "test-data/coercion_gold_all_posts_withroot.csv"
    # Two extra args: allow overriding input/output
    elif len(sys.argv) == 3:
        input_csv = sys.argv[1]
        output_csv = sys.argv[2]
    else:
        print("Usage: python correct_origianl_url.py [input.csv output.csv]")
        sys.exit(1)

    rows = []
    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "URL" not in reader.fieldnames or "Labels" not in reader.fieldnames:
            raise ValueError("Input CSV must have columns: URL, Labels")

        for row in reader:
            url = row["URL"]
            corrected = get_root_url_for_post_url(url)
            # 新列：Corrected_URL
            row["Corrected_URL"] = corrected
            rows.append(row)

    fieldnames = ["URL", "Labels", "Corrected_URL"]

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "URL": row.get("URL", ""),
                    "Labels": row.get("Labels", ""),
                    "Corrected_URL": row.get("Corrected_URL", ""),
                }
            )

    print(f"Done. Wrote {len(rows)} rows to {output_csv}")


if __name__ == "__main__":
    main()