# ----------------- Imports ----------------- #
import joblib
import re
import tkinter as tk
from tkinter import filedialog
from docx import Document
import requests

# ----------------- Google Fact Check API ----------------- #
API_KEY = "ADD API KEY" 

def fact_check_query(claim):
    url = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
    params = {"query": claim, "key": API_KEY}
    try:
        resp = requests.get(url, params=params)
        data = resp.json()
        return data.get("claims", [])
    except:
        return []

# ----------------- Clean Input ----------------- #
def clean_text(text):
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[^a-zA-Z\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower()

# ----------------- Detect Trusted Source ----------------- #
def detect_trusted_source(text):
    lower_text = text.lower()

    known_sources = [
        "new york times", "nbc news", "cnn", "reuters", "associated press", "ap",
        "bbc", "washington post", "cbs news", "bloomberg", "npr", "guardian", "abc news", "politico"
    ]

    # Strong match: byline pattern
    byline_match = re.search(
        r'by\s+.+?,\s*(%s)' % '|'.join(known_sources),
        lower_text,
        re.IGNORECASE
    )
    if byline_match:
        return byline_match.group(1).title(), "strong"

    # Medium match: top of article or source credits
    top_chunk = lower_text[:600]
    for source in known_sources:
        if (
            source in top_chunk or
            re.search(r'(credit|photo|image|source).{0,50}' + source, lower_text)
        ):
            return source.title(), "medium"

    # Weak match: anywhere
    for source in known_sources:
        if source in lower_text:
            return source.title(), "weak"

    return None, None

# ----------------- Load Model + Vectorizer ----------------- #
model = joblib.load("fake_news_voting_model.pkl")
vectorizer = joblib.load("tfidf_vectorizer.pkl")

# ----------------- File Upload + Prediction ----------------- #
print("📢 Welcome to the Fake News Detector (.docx + Fact Check Override)")

tk.Tk().withdraw()
file_path = filedialog.askopenfilename(
    title="Select a Word (.docx) file",
    filetypes=[("Word Documents", "*.docx")]
)

if file_path:
    try:
        doc = Document(file_path)
        input_text = "\n".join([para.text for para in doc.paragraphs if para.text.strip() != ""])
        cleaned = clean_text(input_text)
        features = vectorizer.transform([cleaned])
        proba = model.predict_proba(features)[0][1]

        # Detect trusted source
        source_detected, source_confidence = detect_trusted_source(input_text)

        # If not found, ask user
        if not source_detected:
            print("\n🔍 No trusted source automatically detected.")
            manual_input = input("❓ Please type the source name (or leave blank to skip): ").strip().lower()
            known_sources = [
                "new york times", "nbc news", "cnn", "reuters", "associated press", "ap",
                "bbc", "washington post", "cbs news", "bloomberg", "npr", "guardian", "abc news", "politico"
            ]
            if manual_input in known_sources:
                source_detected = manual_input.title()
                source_confidence = "manual"
                print(f"✅ Manual Source Registered: {source_detected}")
            elif manual_input:
                print("⚠️ Unrecognized source, will not be trusted.")
                source_detected = None

        print(f"\n🔍 Model Confidence for REAL: {proba:.2f}")
        print(f"[DEBUG] Detected Source: {source_detected}, Confidence: {source_confidence}")

        # ----------------- Decision Logic ----------------- #
        if source_detected and source_confidence in ["strong", "medium", "manual"] and proba < 0.5:
            print("\n⚠️ Trusted source detected but model is confident it's FAKE.")
            print("🔄 Overriding classification to RUMOR due to credible uncertainty.")
            final_decision = "RUMOR"

        elif proba >= 0.65:
            print("\n✅ Model says: REAL")
            final_decision = "REAL"

            if proba < 0.9:
                print("⚠️ Running Fact-Check to confirm...")
                fact_results = fact_check_query(cleaned[:300])
                if fact_results:
                    top = fact_results[0]["claimReview"][0]
                    rating = top["textualRating"].lower()
                    source = top["publisher"]["name"]
                    url = top["url"]
                    print(f"🧾 Fact Check Rating: {top['textualRating']} (Source: {source})")
                    if "false" in rating or "pants" in rating:
                        print(f"\n❌ Fact-Check contradicts model. FINAL DECISION: FAKE")
                        print(f"• Source: {source}")
                        print(f"• Rating: {top['textualRating']}")
                        print(f"• Link: {url}")
                        final_decision = "FAKE"
                else:
                    print("⚠️ No fact-check found.")

        elif 0.45 <= proba < 0.65:
            print("\n⚠️ Model says: RUMOR")
            final_decision = "RUMOR"

        else:
            print("\n🤖 Model says: FAKE")
            final_decision = "FAKE"

            print("🔎 Running Fact-Check to confirm...")
            fact_results = fact_check_query(cleaned[:300])
            if fact_results:
                top = fact_results[0]["claimReview"][0]
                rating = top["textualRating"].lower()
                source = top["publisher"]["name"]
                url = top["url"]
                print(f"🧾 Fact Check Rating: {top['textualRating']} (Source: {source})")
                if "true" in rating or "mixture" in rating or "mostly true" in rating:
                    print(f"\n🟨 Fact-Check disagrees with model. FINAL DECISION: REAL")
                    print(f"• Source: {source}")
                    print(f"• Rating: {top['textualRating']}")
                    print(f"• Link: {url}")
                    final_decision = "REAL"

        # ----------------- Final Result ----------------- #
        emoji = {"REAL": "✅", "FAKE": "❌", "RUMOR": "⚠️"}.get(final_decision, "❓")
        print(f"\n🧾 {emoji} FINAL DECISION: This article is MOST LIKELY **{final_decision}**.")

    except Exception as e:
        print(f"❌ Error reading .docx file: {e}")
else:
    print("⚠️ No file selected.")