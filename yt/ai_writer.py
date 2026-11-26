"""
Ask an AI for YouTube Shorts SEO text (title, intro, learn points, keywords, hashtags, tags).
Order: Groq -> GitHub Models -> Gemini (Gemini last: its free quota is needed by the Generate loop).
Returns a dict or None.

Env: GEMINI_API_KEY, GEMINI_API_KEY_2.._9 (or GEMINI_API_KEYS="k1,k2"), GROQ_API_KEY,
     GITHUB_TOKEN / GH_MODELS_TOKEN (GitHub Models, free inside Actions).
"""

import json
import os
import re
import time

import requests

GEMINI_MODELS = [os.environ.get("GEMINI_MODEL", "gemini-flash-latest"), "gemini-flash-lite-latest"]
BACKUPS = [
    ("groq", "https://api.groq.com/openai/v1/chat/completions", ("GROQ_API_KEY",),
     os.environ.get("GROQ_MODELS", "openai/gpt-oss-120b,qwen/qwen3.8-27b")),
    ("github", "https://models.github.ai/inference/chat/completions", ("GH_MODELS_TOKEN", "GITHUB_TOKEN"),
     os.environ.get("GITHUB_MODELS", "openai/gpt-4.1-mini,openai/gpt-4o-mini")),
]

PROMPT = """You are the YouTube Shorts SEO writer for "The 30 Sec Dev" (@the30sec_dev), an Indian channel that
teaches SQL in 30-60 second Shorts in Roman Hinglish (Hindi written in English letters, mixed with English tech words).
Audience: Indian students, freshers, data analyst / backend job seekers preparing for SQL interviews.

Write the YouTube text for this Short:
- Series part: {part}
- Topic: {topic}
- Module: {module}
- Hook used in the video: {hook}
- What the video teaches: {points}
- Example query shown: {code}
- Common mistake covered: {mistake}

LANGUAGE RULE: title, intro, learn and keywords must be in Roman Hinglish (Hindi words in English letters mixed
with English tech words, e.g. "NULL zero nahi hota, isliye IS NULL use karo"). Never write full English sentences
and never use Devanagari script. SQL keywords stay in English.

Return ONLY a JSON object with these keys:
"title": max 80 characters. Must contain the exact topic keyword ("{topic}") and the word SQL, plus a curiosity
         hook in Hinglish that makes people click (question, surprise, interview angle, or relatable desi example),
         1-2 emojis. No clickbait lies. Do NOT add #shorts (added later).
"intro": 2-3 short lines in Hinglish, strong hook first, naturally using search phrases like
         "{topic} in SQL", "SQL in Hindi", "SQL interview".
"learn": 4-6 short bullet strings in Roman Hinglish (no emoji, no numbering) of what the viewer learns. Technically correct.
"keywords": one Hinglish/English sentence packed with natural search phrases people type on YouTube for this topic
            (for example "{topic} in SQL in Hindi", "{topic} SQL interview question", "SQL tutorial for beginners").
"hashtags": 12 popular, currently trending hashtags for SQL / data / coding / tech Shorts in India, most relevant first,
            including 2-3 topic-specific ones. Lowercase, start with #, no spaces. Do NOT include #shorts.
"tags": 30 YouTube search tags (no #), mix of topic-specific long-tail phrases (Hindi + English) and broad ones
        like "sql tutorial in hindi", "sql interview questions". Each under 30 characters.
"""


def gemini_keys():
    names = ["GEMINI_API_KEY"] + [f"GEMINI_API_KEY_{i}" for i in range(2, 10)]
    keys = [os.environ.get(n, "").strip() for n in names]
    keys += [k.strip() for k in os.environ.get("GEMINI_API_KEYS", "").split(",")]
    return list(dict.fromkeys(k for k in keys if k))


def parse(text):
    text = re.sub(r"^```(json)?|```$", "", (text or "").strip())
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


def ask_gemini(prompt):
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.9}}
    for key in gemini_keys():
        for model in GEMINI_MODELS:
            try:
                r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                  headers={"x-goog-api-key": key}, json=body, timeout=120)
                if not r.ok:
                    print(f"  gemini {model}: {r.status_code}", flush=True)
                    continue
                return parse(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            except (requests.RequestException, ValueError, KeyError, IndexError) as e:
                print(f"  gemini {model}: failed ({type(e).__name__})", flush=True)
    return None


def ask_backup(prompt):
    for name, url, key_vars, models in BACKUPS:
        key = next((os.environ[v].strip() for v in key_vars if os.environ.get(v, "").strip()), "")
        if not key:
            continue
        for model in [m.strip() for m in models.split(",") if m.strip()]:
            try:
                r = requests.post(url, headers={"Authorization": f"Bearer {key}"}, timeout=120, json={
                    "model": model, "temperature": 0.9,
                    "messages": [{"role": "user", "content": prompt + "\n\nAnswer with ONLY the JSON object."}]})
                if not r.ok:
                    print(f"  {name} {model}: {r.status_code}", flush=True)
                    continue
                return parse(r.json()["choices"][0]["message"]["content"])
            except (requests.RequestException, ValueError, KeyError, IndexError) as e:
                print(f"  {name} {model}: failed ({type(e).__name__})", flush=True)
    return None


def valid(a):
    return (isinstance(a, dict) and isinstance(a.get("title"), str) and 10 <= len(a["title"]) <= 100
            and isinstance(a.get("intro"), str) and isinstance(a.get("learn"), list) and len(a["learn"]) >= 3
            and isinstance(a.get("hashtags"), list) and isinstance(a.get("tags"), list) and len(a["tags"]) >= 10)


def write(part, topic, module, hook, points, code, mistake):
    prompt = PROMPT.format(part=part, topic=topic, module=module or "-", hook=hook or "-",
                           points="; ".join(points) or "-", code=(code or "-").replace("\n", " "),
                           mistake=mistake or "-")
    for attempt in range(2):
        a = ask_backup(prompt) or ask_gemini(prompt)
        if valid(a):
            return a
        print(f"  AI answer missing or invalid (attempt {attempt + 1})", flush=True)
        time.sleep(5)
    return None
