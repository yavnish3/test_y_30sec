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
    git("add", "yt/yt_posted.csv", "yt/yt_videos.csv", check=False)
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
    code = subprocess.run([sys.executable, "-u", "upload_next.py"], cwd=HERE).returncode
    save()
    if code not in (0, 3):
        print(f"upload_next.py failed with exit code {code}")


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
    main()
