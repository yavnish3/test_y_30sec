"""Build yt_videos.csv."""

import csv
import os
import sys
import time

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


def load_env():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def is_template(r):
    return "\nIs video mein: " in r.get("description", "")


def main():
    load_env()
    use_ai = "--no-ai" not in sys.argv
    rows = {} if "--all" in sys.argv else load()
    redo = "--redo-template" in sys.argv
    for pid, row in sorted(fetch_queue().items()):
        if pid not in rows or (redo and is_template(rows[pid])):
            rows[pid] = build(pid, row, use_ai=use_ai)
            print(f"{pid}: {rows[pid]['title']}", flush=True)
            save(rows)
            if use_ai:
                time.sleep(4)
    save(rows)
    print(f"{len(rows)} rows in {PATH}")


if __name__ == "__main__":
    main()
