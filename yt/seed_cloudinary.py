"""
One-time, on your Mac: copy the hand-made reels (SQL001-081) to Cloudinary yt/reel/
so the YouTube loop can upload them. New reels (SQL082+) are added there by the
generator in test_in_up automatically.

    ../.venv/bin/python test_y_30sec/yt/seed_cloudinary.py ~/Documents/Code/web/test_vid_post/output
Reads CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET from in_up/.env.
Also copies AI reels (SQL082+) from insta/reel inside Cloudinary. Skips ids already uploaded to YouTube and files already on Cloudinary.
"""

import csv
import glob
import hashlib
import os
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def env():
    vals = {}
    path = os.path.join(HERE, "..", "..", ".env")
    for line in open(path, encoding="utf-8"):
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def main():
    src = os.path.expanduser(sys.argv[1])
    e = env()
    cloud, key, secret = e["CLOUDINARY_CLOUD_NAME"], e["CLOUDINARY_API_KEY"], e["CLOUDINARY_API_SECRET"]
    with open(os.path.join(HERE, "yt_posted.csv"), encoding="utf-8") as f:
        done = {r["id"] for r in csv.DictReader(f)}
    files = {os.path.basename(p)[:-4]: p for p in glob.glob(os.path.join(src, "SQL*.mp4"))}
    queue = os.path.join(HERE, "..", "..", "test_in_up", "scheduler", "sql_reel_posts.csv")
    with open(queue, encoding="utf-8-sig") as f:  # AI reels: copy from insta/reel inside Cloudinary
        for r in csv.DictReader(f):
            files.setdefault(r["id"], f"https://res.cloudinary.com/{cloud}/video/upload/insta/reel/{r['id']}.mp4")
    for pid, path in sorted(files.items()):
        url = f"https://res.cloudinary.com/{cloud}/video/upload/yt/reel/{pid}.mp4"
        if pid in done or requests.head(url, timeout=30).ok:
            print(f"{pid}: skip")
            continue
        params = {"public_id": f"yt/reel/{pid}", "asset_folder": "yt/reel", "overwrite": "true",
                  "timestamp": str(int(time.time()))}
        sig = "&".join(f"{k}={params[k]}" for k in sorted(params)) + secret
        params.update(api_key=key, signature=hashlib.sha1(sig.encode()).hexdigest())
        api = f"https://api.cloudinary.com/v1_1/{cloud}/video/upload"
        if path.startswith("http"):
            if not requests.head(path, timeout=30).ok:
                print(f"{pid}: not on Cloudinary, skip")
                continue
            resp = requests.post(api, data={**params, "file": path}, timeout=900)
        else:
            with open(path, "rb") as f:
                resp = requests.post(api, data=params, files={"file": f}, timeout=900)
        print(f"{pid}: {'ok' if resp.ok else resp.text[:150]}", flush=True)


if __name__ == "__main__":
    main()
