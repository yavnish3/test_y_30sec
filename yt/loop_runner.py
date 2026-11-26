"""
Self-restarting YouTube loop: each GitHub Actions run sleeps until the next upload
slot, uploads one Short with upload_next.py, saves yt_posted.csv and ends; the workflow
then starts a fresh run of itself. A run that cannot reach a slot within ~5.5 h just
ends and the next run keeps waiting.

Schedule: one Short every 4 hours, counted from the last upload in yt_posted.csv
(6 a day; YouTube's free API quota allows about 6 uploads a day).
UPLOAD_NOW=yes uploads right away (hand-started runs only).
"""

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EVERY = timedelta(hours=4)
BUDGET = 5 * 3600 + 30 * 60
START = time.time()


def last_upload():
    import csv
    with open(os.path.join(HERE, "yt_posted.csv"), encoding="utf-8") as f:
        times = [datetime.fromisoformat(r["posted_at"]) for r in csv.DictReader(f) if r.get("posted_at")]
    times = [t if t.tzinfo else t.replace(tzinfo=timezone.utc) for t in times]
    return max(times) if times else None


def next_slot(now):
    last = last_upload()
    return max(last + EVERY, now) if last else now


def git(*args, check=True):
    return subprocess.run(["git", *args], cwd=ROOT, check=check)


def save():
    git("add", "yt/yt_posted.csv", "yt/yt_videos.csv", "yt/last_run.log", check=False)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return
    git("commit", "-m", "Update yt_posted.csv / yt_videos.csv")
    for _ in range(5):
        try:
            git("pull", "--rebase")
            git("push")
            return
        except subprocess.CalledProcessError:
            time.sleep(10)
    print("Warning: could not push yt_posted.csv")


def upload_once():
    git("pull", "--rebase", check=False)
    need = ["YT_REFRESH_TOKEN", "MEDIA_BASE_URL", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"]
    missing = [n for n in need if not os.environ.get(n, "").strip()]
    if not (os.environ.get("YT_CLIENT_JSON", "").strip() or os.environ.get("YT_CLIENT_ID", "").strip()):
        missing.append("YT_CLIENT_JSON")
    ai = [n for n in ("GROQ_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_2") if os.environ.get(n, "").strip()]
    head = (f"run at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC\n"
            f"missing secrets: {missing or 'none'} | AI keys set: {ai}\n")
    proc = subprocess.run([sys.executable, "-u", "upload_next.py"], cwd=HERE, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out, flush=True)
    code = proc.returncode
    tail = "\n".join(l for l in out.splitlines() if not l.startswith((' "description"', '  "description"')))[-3000:]
    with open(os.path.join(HERE, "last_run.log"), "w", encoding="utf-8") as f:  # readable without logging in
        f.write(head + f"exit code: {code}\n\n" + tail + "\n")
    save()
    if code != 0:  # failed or nothing ready: wait before the next run, never restart in a tight loop
        pause()


def pause():
    """Wait up to 1 h before the next run, but stay inside GitHub's 6 h job limit
    (if the job is killed by the timeout, the next run is never started)."""
    wait = max(0, min(3600, BUDGET + 15 * 60 - (time.time() - START)))
    print(f"Waiting {wait / 60:.0f} min before the next try", flush=True)
    time.sleep(wait)


def main():
    if os.environ.get("UPLOAD_NOW") == "yes":
        upload_once()
        return
    git("pull", "--rebase", check=False)  # latest yt_posted.csv (a hand-started upload may have run)
    now = datetime.now(timezone.utc)
    slot = next_slot(now)
    left = BUDGET - (time.time() - START)
    wait = (slot - now).total_seconds()
    print(f"Next upload slot: {slot:%Y-%m-%d %H:%M} UTC (in {wait / 3600:.1f} h)", flush=True)
    if wait > left:
        print(f"Slot is beyond this run; sleeping {left / 3600:.1f} h then restarting", flush=True)
        time.sleep(max(0, left))
        return
    time.sleep(max(0, wait))
    upload_once()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 - any crash: pause, so the restart is never a tight loop
        print(f"loop_runner error: {type(e).__name__}: {e}", flush=True)
        pause()
