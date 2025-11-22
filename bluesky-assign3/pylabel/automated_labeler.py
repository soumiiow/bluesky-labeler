"""Implementation of automated moderator"""

from typing import List
from atproto import Client
from .label import post_from_url
import pandas as pd
import ahocorasick
import re

# Valid labels allowed to be returned
label_names = set([
    "sexual violence",
    "emotional coercion",
    "reputational coercion",
    "self harm",
    "survivor discussion",
    "fictional depiction",
    "traumatic news"
])

# Labels that increase severity more heavily
CRITICAL_LABELS = {"sexual violence", "self harm"}


class AutomatedLabeler:
    """Automated labeler implementation"""

    def __init__(self, client: Client, input_dir):
        self.client = client

        # Load both regex and literal phrases from the unified CSV
        self.literal_lexicon, self.regex_patterns = self.load_lexicon(f"{input_dir}/lexicon.csv")

        # Build automaton only from literal (non-regex) entries
        self.phrase_automaton = self.build_automaton(self.literal_lexicon)
        
        # Load human-review signaling keywords
        self.review_literals, self.review_regexes = self.load_review_keywords(f"{input_dir}/review-lexicon.csv")

    def load_lexicon(self, filepath: str):
        """
        Loads lexicon.csv which contains:
        category,phrase_or_pattern,is_regex,notes

        Returns:
            literal_map: dict → phrase -> category
            regex_patterns: list → (compiled_regex, category)
        """
        df = pd.read_csv(filepath)

        literal_map = {}
        regex_patterns = []

        for _, row in df.iterrows():
            category = row["category"].lower()
            phrase = row["phrase_or_pattern"]
            is_regex = str(row["is_regex"]).strip().upper() == "TRUE"

            if is_regex:
                # Try compiling and add to regex patterns list
                try:
                    regex = re.compile(phrase, re.IGNORECASE)
                    regex_patterns.append((regex, category))
                except re.error as e:
                    print(f"[WARN] Invalid regex skipped: {phrase} ({e})")
            else:
                # Literal phrase goes into automaton
                literal_map[phrase.lower()] = category

        return literal_map, regex_patterns
    
    def load_review_keywords(self, filepath: str):
        """Load review-trigger keywords from CSV into two lists: regex and literal."""
        df = pd.read_csv(filepath)

        literal = []
        regex = []
        
        for _, row in df.iterrows():
            phrase = row["phrase_or_pattern"]
            if row["is_regex"] or str(row["is_regex"]).upper() == "TRUE":
                try:
                    regex.append(re.compile(phrase, re.IGNORECASE))
                except re.error as e:
                    print(f"[WARN] Invalid review regex skipped: {phrase} ({e})")
            else:
                literal.append(phrase.lower())
        
        return literal, regex
    

    def build_automaton(self, lexicon_map):
        A = ahocorasick.Automaton()
        for phrase, label in lexicon_map.items():
            A.add_word(phrase, (phrase, label))
        A.make_automaton()
        return A

    def moderate_post(self, url: str) -> List[str]:
        """
        Apply moderation to the given Bluesky post URL.
        Returns a list of labels.
        """
        post = post_from_url(self.client, url)
        content = post.value.text.lower()

        labels = set()
        matches_found = set()
        severity_score = 0
        
        # Check for literal phrases using Aho-Corasick automaton
        for end_idx, (phrase, category) in self.phrase_automaton.iter(content):
            if category in label_names and phrase not in matches_found:
                labels.add(category)
                matches_found.add(phrase)
                severity_score += 2 if category in CRITICAL_LABELS else 1

        # Check for regex patterns
        for regex, category in self.regex_patterns:
            if regex.search(content) and regex.pattern not in matches_found:
                if category in label_names:
                    labels.add(category)
                    matches_found.add(regex.pattern)
                    severity_score += 2 if category in CRITICAL_LABELS else 1

        if severity_score >= 6:
            severity_level = 3
        elif severity_score >= 3:
            severity_level = 2
        else:
            severity_level = 1

        labels.add(f"severity-level-{severity_level}")
        
        # Check for human review keywords
        needs_review = False
        for review_word in self.review_literals:
            if review_word in content:
                labels.add("human-review")
                needs_review = True
                break
        if not needs_review:
            for review_regex in self.review_regexes:
                if review_regex.search(content):
                    labels.add("human-review")
                    break

        return list(labels)
