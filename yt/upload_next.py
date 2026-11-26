"""
Upload the next SQL reel to YouTube as a Short.

Videos:   Cloudinary video/upload/insta/reel/SQLxxx.mp4, ONE copy shared with the Instagram
          loop (test_in_up). A video is deleted only once it is on both Instagram and YouTube.
Captions: sql_reel_posts.csv from the public yavnish3/test_in_up repo (same text as Instagram).
Progress: yt_posted.csv (id, video_id, posted_at). Posted ids are never uploaded again.

Env: YT_CLIENT_JSON (or YT_CLIENT_ID + YT_CLIENT_SECRET), YT_REFRESH_TOKEN, MEDIA_BASE_URL,
     CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, optional YT_PRIVACY (public|unlisted|private).

    python upload_next.py            # upload one
    python upload_next.py --dry-run  # show what would be uploaded
Exit code 0 = uploaded, 3 = nothing ready, other = error.
"""

import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
POSTED = os.path.join(HERE, "yt_posted.csv")
QUEUE_URL = "https://raw.githubusercontent.com/yavnish3/test_in_up/main/scheduler/sql_reel_posts.csv"
EXTRA_TAGS = ["sql", "learn sql", "sql in hindi", "sql tutorial", "database", "dbms",
              "data analyst", "sql interview questions", "coding", "programming", "shorts"]


def load_posted():
    with open(POSTED, encoding="utf-8") as f:
        return {r["id"] for r in csv.DictReader(f)}


def mark_posted(pid, video_id):
    with open(POSTED, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([pid, video_id, datetime.now(timezone.utc).isoformat(timespec="seconds")])


def queue():
    resp = requests.get(QUEUE_URL, timeout=30)
    resp.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))
    return sorted(rows, key=lambda r: r["id"])


def clean(text):
    return text.replace("<", "‹").replace(">", "›")  # YouTube rejects < and >


def metadata(item):
    title = clean(item["title"].strip())
    if len(title) + 8 <= 100:
        title += " #shorts"
    title = title[:100]
    tags_line = item.get("hashtags", "").strip()
    desc = clean(f"{item['caption'].strip()}\n\n{tags_line} #shorts\n\n"
                 "Roz SQL seekho, 30 second mein. Subscribe: @the30sec_dev")
    tags, total = [], 0
    for t in [h.lstrip("#") for h in tags_line.split()] + EXTRA_TAGS:
        if t and t not in tags and total + len(t) + 1 <= 450:
            tags.append(t)
            total += len(t) + 1
    return {
        "snippet": {"title": title, "description": desc[:4900], "tags": tags,
                    "categoryId": "27", "defaultLanguage": "hi", "defaultAudioLanguage": "hi"},
        "status": {"privacyStatus": os.environ.get("YT_PRIVACY", "public"),
                   "selfDeclaredMadeForKids": False, "embeddable": True},
    }


def client():
    """Client id/secret from YT_CLIENT_JSON (the whole downloaded credentials JSON) or YT_CLIENT_ID/_SECRET."""
    raw = os.environ.get("YT_CLIENT_JSON", "").strip()
    if raw:
        data = json.loads(raw)
        data = data.get("installed") or data.get("web") or data
        return data["client_id"], data["client_secret"]
    return os.environ["YT_CLIENT_ID"], os.environ["YT_CLIENT_SECRET"]


def access_token():
    cid, secret = client()
    resp = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid,
        "client_secret": secret,
        "refresh_token": os.environ["YT_REFRESH_TOKEN"],
        "grant_type": "refresh_token"}, timeout=30)
    if not resp.ok:
        sys.exit(f"Could not refresh the YouTube token ({resp.status_code}): {resp.text[:200]}\n"
                 "If it says invalid_grant: run get_token.py again and update YT_REFRESH_TOKEN.")
    return resp.json()["access_token"]


def video_url(media, pid):
    return f"{media}/video/upload/insta/reel/{pid}.mp4"


def reachable(url):
    try:
        return requests.head(url, timeout=30, allow_redirects=True).ok
    except requests.RequestException:
        return False


def download(url, path):
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def upload(token, path, meta):
    size = os.path.getsize(path)
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
        data=json.dumps(meta), timeout=60)
    if not init.ok:
        if "quotaExceeded" in init.text or "uploadLimitExceeded" in init.text:
            print("YouTube daily limit reached; will try again at the next slot")
            sys.exit(3)
        sys.exit(f"YouTube upload start failed ({init.status_code}): {init.text[:400]}")
    location = init.headers["Location"]
    for attempt in range(4):
        with open(path, "rb") as f:
            resp = requests.put(location, data=f, timeout=900,
                                headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4",
                                         "Content-Length": str(size)})
        if resp.ok:
            return resp.json()
        print(f"  upload attempt {attempt + 1} failed ({resp.status_code}): {resp.text[:200]}")
        time.sleep(20)
    sys.exit("YouTube upload failed")


IG_POSTED_URL = "https://raw.githubusercontent.com/yavnish3/test_in_up/main/scheduler/posted.csv"


def posted_on_both():
    """Reel ids already on YouTube and on Instagram. Empty if Instagram's list can't be read."""
    try:
        resp = requests.get(IG_POSTED_URL, params={"t": int(time.time())}, timeout=30)
        resp.raise_for_status()
        ig = {r["id"] for r in csv.DictReader(io.StringIO(resp.text))}
    except Exception as e:  # noqa: BLE001
        print(f"Could not read Instagram's posted list ({e}): keeping the video")
        return []
    return sorted(load_posted() & ig)[-100:]  # Cloudinary deletes up to 100 per call


def delete_from_cloudinary(media):
    """insta/reel/<id>.mp4 is shared with the Instagram loop: delete only videos posted on both."""
    key, secret = os.environ.get("CLOUDINARY_API_KEY"), os.environ.get("CLOUDINARY_API_SECRET")
    ids = posted_on_both()
    if not (key and secret and ids):
        print("Nothing to delete from Cloudinary (not posted on Instagram yet, or keys missing)")
        return
    cloud = media.rstrip("/").rsplit("/", 1)[-1]
    try:
        resp = requests.delete(f"https://api.cloudinary.com/v1_1/{cloud}/resources/video/upload",
                               params=[("public_ids[]", f"insta/reel/{i}") for i in ids],
                               auth=(key, secret), timeout=60)
        gone = [i for i, v in resp.json().get("deleted", {}).items() if v == "deleted"]
        print(f"Deleted from Cloudinary (posted on both): {gone}")
    except Exception as e:  # noqa: BLE001 - never fail an upload over cleanup
        print(f"Warning: could not delete from Cloudinary: {e}")


def main():
    dry = "--dry-run" in sys.argv
    media = os.environ["MEDIA_BASE_URL"].rstrip("/")
    posted = load_posted()
    todo = [r for r in queue() if r["id"] not in posted]
    item = None
    for r in todo[:15]:  # first unposted reel whose video is on Cloudinary
        if reachable(video_url(media, r["id"])):
            item = r
            break
        print(f"{r['id']}: no video in insta/reel yet, skipping for now")
    if not item:
        print(f"Nothing ready to upload ({len(todo)} not uploaded yet)")
        sys.exit(3)
    pid, meta = item["id"], metadata(item)
    print(f"Next: {pid}\n{json.dumps(meta, ensure_ascii=False, indent=1)}")
    if dry:
        return
    token = access_token()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"{pid}.mp4")
        download(video_url(media, pid), path)
        print(f"Downloaded {os.path.getsize(path) / 1e6:.1f} MB, uploading to YouTube…", flush=True)
        video = upload(token, path, meta)
    vid = video["id"]
    mark_posted(pid, vid)
    print(f"Uploaded {pid}: https://youtube.com/shorts/{vid}  "
          f"(privacy: {video.get('status', {}).get('privacyStatus')}, "
          f"upload: {video.get('status', {}).get('uploadStatus')})")
    delete_from_cloudinary(media)


if __name__ == "__main__":
    main()
