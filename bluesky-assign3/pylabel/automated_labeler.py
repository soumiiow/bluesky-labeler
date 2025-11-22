"""Implementation of automated moderator"""

from typing import List
from atproto import Client
from .label import post_from_url
import pandas as pd
from PIL import Image
import imagehash
from pathlib import Path
import re

label_names = set(["sexual violence", "emotional coercion", "reputational coercion", "self harm", "survivor discussion", "fictional depiction",
              "traumatic news"])

class AutomatedLabeler:
    """Automated labeler implementation"""

    def __init__(self, client: Client, input_dir):
        # Constructor
        self.client = client
        # load the coersion lexicon into a dictionary with the name of the label as value and words as keys
        self.coercion_lexicon = self.load_into_map(f"{input_dir}/lexicon.csv")
        # coercion regexes   
        self.regex_patterns = self.load_regex_patterns(f"{input_dir}/regex-lexicon.csv")
        
    def load_into_set(self, filepath: str, column_name: str) -> set:
        """Load lines from a file into a set"""
        return set(pd.read_csv(filepath)[column_name].tolist())

    def load_into_map(self, filepath) -> dict:
        """Load lines from a CSV into a dictionary: phrase -> category"""
        df = pd.read_csv(filepath)
        return {row["phrase"].lower(): row["category"].lower() for _, row in df.iterrows()}
    
    def load_regex_patterns(self, filepath: str) -> List[tuple]:
        """Load regex-lexicon.csv as precompiled patterns: (regex, category)"""
        df = pd.read_csv(filepath)
        compiled = []
        for _, row in df.iterrows():
            try:
                regex = re.compile(row["pattern"], re.IGNORECASE)
                compiled.append((regex, row["category"].lower()))
            except re.error as e:
                print(f"[WARN] Skipping invalid regex: {row['pattern']} -> {e}")
        return compiled

    def moderate_post(self, url: str) -> List[str]:
        """
        Apply moderation to the post specified by the given url
        Args:
            url (str): The URL of the Bluesky post to moderate.
        Returns:
            List[str]: A list of labels to be added to the post.
        """
        
        # get post from url
        post = post_from_url(self.client, url)
        # take content and then check for words in the coersion lexicon
        # keep track of labels to be added
        # keep track of words found to avoid duplicate labels
        # for figuring out severity level, we can use a simple count of words found
        content = post.value.text.lower()
        labels = set() # make this a set to avoid duplicate labels
        matches_found = set()
        severity_count = 0
        severity_level = 1 # default to low severity. max is 3
        
        #rework this logic
        for word, label in self.coercion_lexicon.items():
            if word in content and word not in matches_found:
                # if name of label is in the accepted labels, add it
                if label in label_names:
                    labels.add(label)
                    matches_found.add(word)
                    severity_count += 1
                # Check regex patterns
        for regex, label in self.regex_patterns:
            if regex.search(content) and regex.pattern not in matches_found:
                if label in label_names:
                    labels.add(label)
                    matches_found.add(regex.pattern)
                    severity_count += 1

        # based on severity count, we can add additional labels if needed
        if severity_count >= 5:
            severity_level = 3
        elif severity_count >= 3:
            severity_level = 2
        labels.add(f"severity-level-{severity_level}")
        # if severity level is high, we can send it into perspective api for further analysis
        
        # Optional human review for ambiguity
        if any(token in content for token in ["?", "just kidding", "lol"]):
            labels.add("meta:needs-human-review")
        return labels
    
    
    #todo:
    # workshop severity level logic
    # integrate perspective api for high severity posts
    # toxicity score brings up the severity level by 1 if above a certain threshold
    # humor score brings down the severity level by 1 if above a certain threshold
    # humor score could also trigger a human review label