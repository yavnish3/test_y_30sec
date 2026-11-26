"""
YouTube title / description / tags for one reel, built from the test_in_up data:
  scheduler/sql_reel_posts.csv   (hook title, caption, hashtags)
  generator/content/SQLxxx.json  (recap points, example query, common mistake, next topic)

    python build_yt_csv.py   # (re)build yt_videos.csv for every reel
yt_videos.csv can be edited by hand; upload_next.py uses it as is and only builds rows
that are missing (new reels).
"""

import csv
import io
import re

import requests

RAW = "https://raw.githubusercontent.com/yavnish3/test_in_up/main"
FIELDS = ["id", "title", "description", "tags"]

# Description: YouTube ignores ALL hashtags if a video has more than 15.
BASE_HASHTAGS = ["#shorts", "#sql", "#sqlinhindi", "#learnsql", "#sqltutorial", "#sqlforbeginners",
                 "#sqlinterview", "#dataanalyst", "#mysql", "#postgresql", "#database", "#coding", "#programming"]
MAX_HASHTAGS = 15
# Hidden tags field: up to 500 characters in total.
BASE_TAGS = ["sql", "sql in hindi", "learn sql", "sql tutorial", "sql tutorial in hindi", "sql for beginners",
             "sql interview questions", "sql interview questions and answers", "sql queries", "sql query",
             "mysql", "postgresql", "sql server", "database", "dbms", "rdbms", "data analyst",
             "data analytics", "data engineer", "sql course", "sql full course", "sql hindi",
             "sql basics", "learn sql in 30 seconds", "coding in hindi", "programming", "shorts",
             "the 30 sec dev"]
MAX_TAGS_CHARS = 490


def plain(text):
    text = re.sub(r"\[\[|\]\]|\*\*", "", text or "")
    return re.sub(r"\s+", " ", text).strip()


def fetch_queue():
    resp = requests.get(f"{RAW}/scheduler/sql_reel_posts.csv", timeout=30)
    resp.raise_for_status()
    return {r["id"]: r for r in csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig")))}


def fetch_content(pid):
    resp = requests.get(f"{RAW}/generator/content/{pid}.json", timeout=30)
    return resp.json() if resp.ok else {}


def hook_of(row, content):
    title = row.get("title", "")
    hook = title.split("|", 1)[1].strip() if "|" in title else ""
    if not hook or hook.lower() == row.get("topic", "").lower():  # AI reels: title is just the topic
        hook = (row.get("caption") or "").strip().splitlines()[0] if row.get("caption") else plain(content.get("hook"))
    return plain(hook)


def make_title(topic, hook, part):
    for t in (f"{topic} | {hook} | SQL Hindi #{part} #shorts",
              f"{topic} | {hook} #shorts",
              f"{hook} #shorts"):
        if len(t) <= 100:
            return t
    words, out = hook.split(), ""
    for w in words:
        if len(f"{topic} | {out} {w}… #shorts") > 100:
            break
        out = f"{out} {w}".strip()
    return f"{topic} | {out}… #shorts"


def slides(content, kind):
    return [s for s in content.get("slides", []) if s.get("type") == kind]


def learn_points(row, content):
    recap = slides(content, "recap")
    if recap:
        return [plain(p) for p in recap[0].get("points", [])][:6]
    desc = row.get("description", "")
    if desc.startswith("Is reel mein seekho:"):
        body = desc.split(":", 1)[1].split("Example:")[0]
        return [p.strip(" .") for p in body.split(",") if p.strip(" .")][:6]
    return [plain(l.lstrip("✅ ")) for l in (row.get("caption") or "").splitlines() if l.startswith("✅")][:6]


def topic_tags(row, topic):
    t = re.sub(r"[^\w\s()]", " ", topic.lower())
    t = re.sub(r"\s+", " ", t).strip()
    if t.endswith(("hai", "hain", "chahiye")):  # question topics like "database kya hota hai"
        return [t, f"{t} sql", f"{t} in hindi"] + [h.lstrip("#") for h in (row.get("hashtags") or "").split() if h.startswith("#")]
    tags = [t, f"{t} in sql", f"sql {t}", f"{t} sql in hindi", f"{t} sql interview question"]
    tags += [h.lstrip("#") for h in (row.get("hashtags") or "").split() if h.startswith("#")]
    if row.get("module"):
        tags.append(f"sql {row['module'].lower()}")
    return tags


def build(pid, row, content=None):
    content = content if content is not None else fetch_content(pid)
    topic = plain(row.get("topic") or content.get("topic") or pid)
    part = int(re.sub(r"\D", "", pid) or 0)
    hook = hook_of(row, content)
    module = row.get("module") or content.get("module") or ""
    nxt = plain(content.get("next", ""))
    if not nxt:
        m = re.search(r"Next:\s*(.+)", row.get("caption") or "")
        nxt = m.group(1).strip() if m else ""

    lines = [hook, "", f"📌 SQL Series Part {part}: {topic}" + (f"  ({module})" if module else ""), ""]
    pts = learn_points(row, content)
    if pts:
        lines += ["Is Short mein seekho:"] + [f"✅ {p}" for p in pts] + [""]
    code = next((s.get("code") for s in slides(content, "code") if s.get("code")), "")
    if not code:
        m = re.search(r"Example:\s*(.+)$", row.get("description", ""))
        code = m.group(1).strip() if m else ""
    if code:
        lines += ["💻 Example query:", code.strip(), ""]
    mistake = slides(content, "mistake")
    if mistake:
        mk = mistake[0]
        lines += [f"❌ Common mistake: {plain(mk.get('wrong'))}",
                  f"✔️ Sahi tareeka: {plain(mk.get('right'))}"]
        if mk.get("why"):
            lines.append(f"💡 Kyun: {plain(mk.get('why'))}")
        lines.append("")
    else:
        m = re.search(r"Galti mat karna:\s*(.+)", row.get("caption") or "")
        if m:
            lines += [f"❌ Common mistake: {m.group(1).strip()}", ""]
    if nxt:
        lines += [f"➡️ Next video: {nxt}", ""]
    lines += [
        "━━━━━━━━━━━━━━━━━━",
        "🚀 The 30 Sec Dev: roz SQL seekho, sirf 30 second mein, simple Hinglish mein.",
        "Data analyst, backend developer, data engineer aur SQL interview ki taiyari ke liye",
        "SELECT se le kar JOINs, window functions, CTE, indexes aur query optimization tak, step by step.",
        "",
        "🔔 Subscribe karo aur bell dabao: @the30sec_dev",
        "📸 Instagram par carousel notes: @the30secdev",
        "💾 Video save kar lo, interview se pehle revise karna.",
        "",
        "Is video mein: " + ", ".join(dict.fromkeys(
            [topic, f"{topic.rstrip('?')} in SQL" if not topic.endswith("?") else topic, "SQL tutorial in Hindi", "SQL for beginners",
             "SQL interview questions", "MySQL", "PostgreSQL", "DBMS"])),
        "",
    ]
    hashtags = []
    topic_h = [h for h in (row.get("hashtags") or "").split() if h.startswith("#")]
    th = "#" + re.sub(r"\W", "", topic.lower())
    for h in BASE_HASHTAGS[:3] + ([th] if len(th) <= 21 else []) + topic_h + BASE_HASHTAGS[3:]:
        if len(h) > 2 and h.lower() not in hashtags:
            hashtags.append(h.lower())
    lines.append(" ".join(hashtags[:MAX_HASHTAGS]))
    desc = "\n".join(lines).replace("<", "‹").replace(">", "›")[:4900]

    tags, total = [], 0
    for t in topic_tags(row, topic) + BASE_TAGS:
        t = t.replace("<", "").replace(">", "").strip()
        cost = len(t) + (2 if " " in t else 0) + 1
        if t and t not in tags and total + cost <= MAX_TAGS_CHARS:
            tags.append(t)
            total += cost
    title = make_title(topic, hook, part).replace("<", "‹").replace(">", "›")
    return {"id": pid, "title": title, "description": desc, "tags": ", ".join(tags)}
