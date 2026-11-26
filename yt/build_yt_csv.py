"""
Build yt/yt_videos.csv (YouTube title, long description, tags) for every reel in the queue.

    python yt/build_yt_csv.py            # add rows for reels that are missing
    python yt/build_yt_csv.py --all      # rebuild every row (overwrites hand edits)
"""

import csv
import os
import sys

from yt_meta import FIELDS, build, fetch_queue

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yt_videos.csv")


def load():
    if not os.path.exists(PATH):
        return {}
    with open(PATH, encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def save(rows):
    with open(PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for pid in sorted(rows):
            w.writerow(rows[pid])


def main():
    rows = {} if "--all" in sys.argv else load()
    for pid, row in sorted(fetch_queue().items()):
        if pid not in rows:
            rows[pid] = build(pid, row)
            print(f"{pid}: {rows[pid]['title']}")
    save(rows)
    print(f"{len(rows)} rows in {PATH}")


if __name__ == "__main__":
    main()
