"""Enhanced test script: evaluates label accuracy + severity-level accuracy."""

import json
import os
import pathlib
import sys
import re
import pandas as pd
from atproto import Client
from atproto_client import exceptions as atproto_exceptions
from dotenv import load_dotenv

# -------------------------
# Path setup
# -------------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent
ASSIGN_DIR = BASE_DIR / "bluesky-assign3"
TEST_DATA_DIR = ASSIGN_DIR / "test-data"
LABELER_INPUT_DIR = ASSIGN_DIR / "labeler-inputs"

if str(ASSIGN_DIR) not in sys.path:
    sys.path.insert(0, str(ASSIGN_DIR))

# IMPORTANT: specify which dataset to use
DEFAULT_TEST_FILES = [
    TEST_DATA_DIR / "data.csv"
]

from pylabel import AutomatedLabeler


# -------------------------
# Environment variables
# -------------------------
load_dotenv(override=True)
USERNAME = os.getenv("USERNAME")
PW = os.getenv("PW")


def extract_expected_severity(row):
    """Extract severity level integer from column Severity if exists."""
    if "Severity_level" not in row or pd.isna(row["Severity_level"]):
        return None
    try:
        # Some cases like "3" or "2"
        return int(str(row["Severity_level"]).strip())
    except:
        return None


def extract_predicted_severity(predicted_labels):
    """Find severity-level-X among predicted_labels."""
    for lbl in predicted_labels:
        if lbl.startswith("severity-level-"):
            try:
                return int(lbl.replace("severity-level-", ""))
            except:
                pass
    return None


# -------------------------
# Main evaluation
# -------------------------
def test_labeler(labeler, input_urls: str):
    IGNORE_LABELS = {"meta:needs-human-review"}

    print(f"Testing with input urls {input_urls}")
    df = pd.read_csv(input_urls)

    total_rows = df.shape[0]
    skipped = 0

    # post-level
    exact_label_matches = 0           # label-only accuracy

    # severity-level
    severity_correct = 0              # severity-level accuracy
    severity_total = 0                # only count rows where expected severity exists

    # label-level (multi-label) counts — excludes severity/meta labels
    tp_labels = 0     # predicted and righy
    fp_labels = 0     # predicted but not in the dataset
    fn_labels = 0     # in the dataset but not predicted

    for _, row in df.iterrows():
        url = row["URL"]

        # -------------------------
        # Parse expected labels
        # -------------------------
        raw_labels = row["Labels"]
        if pd.isna(raw_labels) or str(raw_labels).strip() == "":
            expected_labels = set()
        else:
            label_text = str(raw_labels).strip()
            try:
                if label_text.startswith("[") and label_text.endswith("]"):
                    expected_labels = set(json.loads(label_text))
                else:
                    # split by comma or semicolon
                    parts = re.split(r"[;,]", label_text)
                    expected_labels = set(p.strip() for p in parts if p.strip())
            except:
                parts = re.split(r"[;,]", label_text)
                expected_labels = set(p.strip() for p in parts if p.strip())

        expected_core = expected_labels - IGNORE_LABELS

        # -------------------------
        # Extract expected severity
        # -------------------------
        expected_sev = extract_expected_severity(row)

        # -------------------------
        # Predict
        # -------------------------
        try:
            predicted = set(labeler.moderate_post(url))
        except Exception as e:
            print(f"[WARN] skipping {url}: {e}")
            skipped += 1
            continue

        # -------------------------
        # Extract predicted severity
        # -------------------------
        predicted_sev = extract_predicted_severity(predicted)

        # Remove severity-* from labels for fairness
        predicted_core = {lbl for lbl in predicted if not lbl.startswith("severity-level-")}
        predicted_core = predicted_core - IGNORE_LABELS

        # -------------------------
        # Evaluation logic (labels)
        # -------------------------
        overlap = expected_core.intersection(predicted_core)
        missing = expected_core - predicted_core
        extra = predicted_core - expected_core

        # post-level exact match (allow up to one extra predicted label)
        if not missing and len(extra) <= 1:
            exact_label_matches += 1
        else:
            print(f"For {url}:")
            print(f"  predicted labels: {list(predicted_core)}")
            print(f"  expected  labels: {list(expected_core)}")
            print(f"  overlap        : {list(overlap)}")
            print(f"  predicted severity level: {predicted_sev}")
            print(f"  expected severity level:  {expected_sev}")
            print()

        # label-level calculate tp / fp / fn
        tp_labels += len(overlap)
        fp_labels += len(extra)
        fn_labels += len(missing)

        # -------------------------
        # Compare severity
        # -------------------------
        if expected_sev is not None:
            severity_total += 1
            if predicted_sev == expected_sev:
                severity_correct += 1

    tested = total_rows - skipped

    # calculate label-level precision / recall
    if tp_labels + fp_labels > 0:
        label_precision = tp_labels / (tp_labels + fp_labels)
    else:
        label_precision = 0.0

    if tp_labels + fn_labels > 0:
        label_recall = tp_labels / (tp_labels + fn_labels)
    else:
        label_recall = 0.0

    print("\n====== RESULTS ======")
    print(f"Total rows:              {total_rows}")
    print(f"Skipped rows:            {skipped}")
    print(f"Tested rows:             {tested}")
    print()
    print(f"Label-only exact match:  {exact_label_matches}/{tested}")
    print(f"Label-level precision:   {label_precision:.3f}")
    print(f"Label-level recall:      {label_recall:.3f}")
    print(f"Severity accuracy:       {severity_correct}/{severity_total} "
          f"({severity_correct / severity_total if severity_total else 0:.3f})")
    print()

    return (
        tested,
        exact_label_matches,
        severity_correct,
        severity_total,
        skipped,
        tp_labels,
        fp_labels,
        fn_labels,
    )

# -------------------------
# Entry point
# -------------------------
def main():
    client = Client()
    client.login(USERNAME, PW)

    labeler = AutomatedLabeler(client, str(LABELER_INPUT_DIR))

    for test_file in DEFAULT_TEST_FILES:
        test_labeler(labeler, str(test_file))


if __name__ == "__main__":
    main()