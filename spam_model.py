"""
spam_model.py

Provides:
- SpamModel class: train_from_csv, load, save, predict
- A safe rule-based fallback (if no trained model available)

Expected CSV format for training:
- Columns: 'label' (values: 'spam' or 'ham'), 'text' (email body+subject or concatenated)
"""
from __future__ import annotations
import os
from typing import Optional
import joblib
import re
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB

MODEL_DIR = "models"
DEFAULT_MODEL_PATH = os.path.join(MODEL_DIR, "spam_model.joblib")


class SpamModel:
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or DEFAULT_MODEL_PATH
        self.pipeline: Optional[Pipeline] = None
        if os.path.exists(self.model_path):
            self.load(self.model_path)

    def load(self, path: str):
        self.pipeline = joblib.load(path)

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self.pipeline, path)

    @classmethod
    def train_from_csv(cls, csv_path: str, out_path: str = DEFAULT_MODEL_PATH):
        """
        Train a simple Tfidf + MultinomialNB model.
        CSV must have columns: 'label' ('spam' or 'ham'), 'text'
        """
        df = pd.read_csv(csv_path)
        if "label" not in df.columns or "text" not in df.columns:
            raise ValueError("CSV must contain 'label' and 'text' columns")

        X = df["text"].fillna("").astype(str)
        y = df["label"].map(lambda v: 1 if str(v).lower().startswith("spam") else 0)

        pipeline = Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), max_features=20000)),
                ("nb", MultinomialNB()),
            ]
        )
        pipeline.fit(X, y)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        joblib.dump(pipeline, out_path)
        print(f"Trained model saved to {out_path}")
        return out_path

    def predict(self, text: str) -> dict:
        """
        Returns: { 'is_spam': bool, 'score': float }
        If model present uses model probability; otherwise uses rule_based detector.
        """
        txt = text or ""
        if self.pipeline is not None:
            proba = float(self.pipeline.predict_proba([txt])[0][1])  # probability of spam
            return {"is_spam": proba >= 0.5, "score": proba}
        else:
            return rule_based_detection(txt)

# Simple rule-based fallback detection
SPAM_KEYWORDS = [
    r"free\b", r"buy now", r"limited time", r"winner", r"congratulat", r"claim prize",
    r"click here", r"urgent", r"act now", r"cheap\b", r"\$\d+", r"viagra", r"lottery"
]

URL_RE = re.compile(r"https?://\S+")
EXCLAMATION_RE = re.compile(r"!{2,}")

def rule_based_detection(text: str) -> dict:
    text_l = text.lower()
    score = 0.0

    # keyword matches
    for kw in SPAM_KEYWORDS:
        if re.search(kw, text_l):
            score += 0.25

    # too many exclamation marks
    if EXCLAMATION_RE.search(text):
        score += 0.15

    # many links
    urls = URL_RE.findall(text)
    if len(urls) >= 2:
        score += 0.2
    elif len(urls) == 1:
        score += 0.08

    # sender spoofing heuristics can be added here (not available in plain text analysis)

    # clamp
    score = min(score, 1.0)
    is_spam = score >= 0.5
    return {"is_spam": is_spam, "score": score}
