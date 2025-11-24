"""Script for testing the automated labeler -- grading mode"""

import json
import os

import pandas as pd
from atproto import Client
from dotenv import load_dotenv

from pylabel import AutomatedLabeler

load_dotenv(override=True)
USERNAME = os.getenv("USERNAME")
PW = os.getenv("PW")


def test_labeler(labeler, input_urls: str):
    """
    Test labeler with particular input urls
    """
    print(f"Testing with input urls {input_urls}")
    urls = pd.read_csv(input_urls)
    num_correct, total = 0, urls.shape[0]
    for _index, row in urls.iterrows():
        url, expected_labels = row["URL"], json.loads(row["Labels"])
        labels = labeler.moderate_post(url)
        if sorted(labels) == sorted(expected_labels):
            num_correct += 1
        else:
            print(f"For {url}, labeler produced {labels}, expected {expected_labels}")
    print(
        f"The labeler produced {num_correct} correct labels assignments out of {total}"
    )
    print(f"Overall ratio of correct label assignments {num_correct/total}")
    return (num_correct, total)


def main():
    """
    Main function for the test script
    """
    client = Client()
    client.login(USERNAME, PW)
    labeler = AutomatedLabeler(client, "labeler-inputs")

    overall_results = []
    # later we will create this CSV with our gold coercion labels
    for input_urls in [
        "test-data/coercion_gold.csv",
    ]:
        overall_results.append(test_labeler(labeler, input_urls))


    print("Overall results:", overall_results)
    num_correct = sum(res[0] for res in overall_results)
    num_total = sum(res[1] for res in overall_results)
    print(f"Total {num_correct} correct out of {num_total}")

if __name__ == "__main__":
    main()
