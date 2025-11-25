# Bluesky Coercion Labeler – CS5342 Assignment 3

This repository contains my implementation of the **coercion labeler** and the **evaluation script** for CS5342 Trust & Safety (Assignment 3).  
The system is lexicon-based and evaluated with **multi-label metrics** (exact-match + label-level precision/recall).

---

## Repository Structure

```text
├── bluesky-assign3/
│   │
│   ├── labeler-inputs/              # All lexicons and indicator lists
│   │   ├── lexicon.csv
│   │   ├── meta-label.csv
│   │   ├── regex-lexicon.csv
│   │   └── tw-indicators.csv
│   │
│   ├── pylabel/                     # Main labeler logic
│   │   ├── __init__.py
│   │   ├── automated_labeler.py     # Coercion labeler entry point
│   │   └── label.py                 # Shared helpers
│   │
│   └── test-data/
│   │   └── coercion_gold_final_posts.csv   # Final gold test set (URLs + labels)
│   │
│   └── .env-TEMPLATE                 #configure your bluesky password and social account
│
├── posts_data/
│   └── all_posts_uri_cid.csv        # Cached post URIs / CIDs (used by grader)
│
├── coercion_test.py               # Test: runs labeler on the gold set and scores it
├── transform_uri2url.py             # Utility to convert URIs → public bsky URLs
└── README.md
```

---

## Running the Labeler & Evaluation

This project does **not** require running a separate test_labeler script.  
The evaluation script automatically:
1. Runs the automated coercion labeler
2. Fetches posts (if needed)
3. Compares predicted labels to the gold dataset
4. Outputs exact‑match + precision/recall scores

### 1. Install dependencies
```
pip install -r requirements.txt
```

### 2. Add credentials  
Copy `.env-TEMPLATE` → `.env`:

```
USERNAME=your_handle.bsky.social
PW=your_app_password
```

### 3. Run the test file (this runs everything including the labeler)
```
python3 coercion_test.py
```

This evaluates predictions against:

```
bluesky-assign3/test-data/coercion_gold_final_posts.csv
```

---

## Final Test Results

From the final dataset of **152 valid posts** (2 skipped due to API errors):

| Metric                 | Score          |
|------------------------|----------------|
| Exact-Match Accuracy   | **46.7% (71/152)** |
| Label-Level Precision  | **0.29**       |
| Label-Level Recall     | **0.29**       |

### Interpretation
- The system intentionally **over-warns** to avoid missing harmful content.  
- Exact-match is conservative because adding *any extra label* becomes incorrect.  
- Precision/recall symmetry reflects limitations of pure lexicon rules.

---

## Notes

- The meta-label `needs-human-review` is **ignored** during evaluation.
- Missing URLs in the API are skipped with a warning.
- This repository contains both the implementation and the report materials.

---

## Author
Diana Cristea
Huijia Shen
Soumya Duriseti