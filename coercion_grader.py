"""Script for testing the automated labeler -- grading mode"""

import json
import os
import pathlib
import sys

# Resolve important paths relative to this file.
BASE_DIR = pathlib.Path(__file__).resolve().parent
ASSIGN_DIR = BASE_DIR / "bluesky-assign3"
TEST_DATA_DIR = ASSIGN_DIR / "test-data"
LABELER_INPUT_DIR = ASSIGN_DIR / "labeler-inputs"

# Ensure we can import the pylabel package that lives in bluesky-assign3/pylabel
if str(ASSIGN_DIR) not in sys.path:
    sys.path.insert(0, str(ASSIGN_DIR))

DEFAULT_TEST_FILES = [
    # TEST_DATA_DIR / "coercion_gold_mini.csv",
    # TEST_DATA_DIR / "coercion_gold.csv",
    TEST_DATA_DIR / "coercion_gold_all_posts.csv",
]

import pandas as pd
from atproto import Client
from atproto_client import exceptions as atproto_exceptions
from dotenv import load_dotenv

from pylabel import AutomatedLabeler

load_dotenv(override=True)
USERNAME = os.getenv("USERNAME")
PW = os.getenv("PW")


def test_labeler(labeler, input_urls: str):
    """
    Test labeler with partial-credit scoring.
    - Exact match still counted.
    - Also compute:
        * label_precision = |pred ∩ gold| / |pred|
        * label_recall    = |pred ∩ gold| / |gold|
    - Skip posts that cause API errors (e.g., BadRequest / missing repo).
    """
    print(f"Testing with input urls {input_urls}")
    df = pd.read_csv(input_urls)

    total_posts = df.shape[0]
    exact_matches = 0

    total_intersection = 0
    total_pred = 0
    total_gold = 0
    skipped = 0

    for _, row in df.iterrows():
        url = row["URL"]
        expected_labels = set(json.loads(row["Labels"]))

        try:
            predicted_labels = set(labeler.moderate_post(url))
        except atproto_exceptions.BadRequestError as e:
            print(f"[WARN] skipping {url}: BadRequestError -> {e}")
            skipped += 1
            continue
        except Exception as e:
            print(f"[WARN] skipping {url}: unexpected error -> {e}")
            skipped += 1
            continue

        intersection = expected_labels.intersection(predicted_labels)

        total_intersection += len(intersection)
        total_pred += len(predicted_labels)
        total_gold += len(expected_labels)

        if predicted_labels == expected_labels:
            exact_matches += 1
        else:
            print(f"For {url}:")
            print(f"  predicted: {list(predicted_labels)}")
            print(f"  expected : {list(expected_labels)}")
            print(f"  overlap  : {list(intersection)}")

    tested_posts = total_posts - skipped
    precision = total_intersection / total_pred if total_pred else 0.0
    recall = total_intersection / total_gold if total_gold else 0.0

    print("\n=== RESULTS ===")
    print(f"Total rows in CSV:        {total_posts}")
    print(f"Skipped (API errors):     {skipped}")
    print(f"Effectively tested posts: {tested_posts}")
    print(f"Exact-match posts:        {exact_matches}/{tested_posts if tested_posts > 0 else 1}")
    print(f"Label-level precision:    {precision:.4f}")
    print(f"Label-level recall:       {recall:.4f}")

    return exact_matches, tested_posts, precision, recall, skipped


def main():
    """
    Main function for the test script
    """
    client = Client()
    client.login(USERNAME, PW)
    labeler = AutomatedLabeler(client, str(LABELER_INPUT_DIR))

    overall_results = []

    for input_path in DEFAULT_TEST_FILES:
        overall_results.append(test_labeler(labeler, str(input_path)))

    print("\n=== OVERALL SUMMARY ===")
    print("Per-file results:", overall_results)

    total_exact = sum(res[0] for res in overall_results)
    total_tested = sum(res[1] for res in overall_results)
    total_skipped = sum(res[4] for res in overall_results)

    print(f"Total exact matches:       {total_exact}/{total_tested if total_tested > 0 else 1}")
    print(f"Total posts tested:        {total_tested}")
    print(f"Total rows skipped (API):  {total_skipped}")


if __name__ == "__main__":
    main()