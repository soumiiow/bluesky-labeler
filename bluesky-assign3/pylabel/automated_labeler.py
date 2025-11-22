"""Implementation of automated moderator"""

from typing import List
from atproto import Client
from .label import post_from_url
import pandas as pd
import ahocorasick
import re

PERSPECTIVE_API_URL = "https://commentanalyzer.googleapis.com/v1/comments:analyze"
#TODO: replace with Perspective API key
PERSPECTIVE_API_KEY = "<API_KEY>"

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
    
    def get_perspective_scores(text: str, attributes=None):
        if attributes is None:
            attributes = ["TOXICITY", "SARCASM", "FLIRTATION", "INSULT", "THREAT", "SEXUAL_EXPLICIT"]

        data = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {attr: {} for attr in attributes}
        }
        response = requests.post(
            f"{PERSPECTIVE_API_URL}?key={PERSPECTIVE_API_KEY}",
            json=data,
            timeout=10
        ).json()
        
        # Extract scores
        scores = {}
        for attr in attributes:
            try:
                scores[attr] = response["attributeScores"][attr]["summaryScore"]["value"]
            except KeyError:
                scores[attr] = 0.0
        return scores
    
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
        
        # Check for human review keywords
        # TODO discuss: bump down severity level by 1 if human review is needed
        needs_review = False
        for review_word in self.review_literals:
            if review_word in content:
                labels.add("human-review")
                needs_review = True
                severity_level = max(1, severity_level - 1)
                break
        if not needs_review:
            for review_regex in self.review_regexes:
                if review_regex.search(content):
                    labels.add("human-review")
                    severity_level = max(1, severity_level - 1)
                    break
        
        # perspective API scoring
        scores = self.get_perspective_scores(content)

        # Humor / sarcasm
        humor_flags = scores.get("SARCASM", 0.0) > 0.7 or scores.get("FLIRTATION", 0.0) > 0.7
        if humor_flags:
            # TODO decide labels.add("meta:humor-detected")
            severity_level -= 1  # downgrade severity

        # Toxicity adjustment
        toxicity = scores.get("TOXICITY", 0.0)
        if toxicity > 0.8:
            severity_score += 1
        elif toxicity >= 0.6:
            severity_level += 0.5
        elif toxicity < 0.3:
            severity_level -= 0.5            
        
        # Final severity level assignment
        if severity_score >= 6:
            severity_level = 3
        elif severity_score >= 3:
            severity_level = 2
        else:
            severity_level = 1
        labels.add(f"severity-level-{severity_level}")
        
        return list(labels)
