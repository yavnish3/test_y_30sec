"""
Upload the next SQL reel to YouTube as a Short.

Videos:   Cloudinary video/upload/insta/reel/SQLxxx.mp4, ONE copy shared with the Instagram
          loop (test_in_up). Cover: insta/thumbnails/SQLxxx.jpg (set as the YouTube thumbnail).
          Both are deleted only once the reel is on both Instagram and YouTube.
Text:     yt_videos.csv (title, long description, tags; built by yt_meta.py from the test_in_up data).
Progress: yt_posted.csv (id, video_id, posted_at). Posted ids are never uploaded again.

Env: YT_CLIENT_JSON (or YT_CLIENT_ID + YT_CLIENT_SECRET), YT_REFRESH_TOKEN, MEDIA_BASE_URL,
     CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET, optional YT_PRIVACY (public|unlisted|private).

    python upload_next.py            # upload one
    python upload_next.py --dry-run  # show what would be uploaded
Exit code 0 = uploaded, 3 = nothing ready, other = error.
"""

import csv
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


VIDEOS = os.path.join(HERE, "yt_videos.csv")  # YouTube title / description / tags (editable by hand)


def video_row(pid, item):
    """Row from yt_videos.csv; builds and appends one (yt_meta.py) for a new reel."""
    from yt_meta import FIELDS, build
    rows = {}
    if os.path.exists(VIDEOS):
        with open(VIDEOS, encoding="utf-8") as f:
            rows = {r["id"]: r for r in csv.DictReader(f)}
    if pid in rows:
        return rows[pid]
    row = build(pid, item)
    new_file = not os.path.exists(VIDEOS)
    with open(VIDEOS, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)
    print(f"{pid}: added to yt_videos.csv")
    return row


def metadata(pid, item):
    row = video_row(pid, item)
    clean = lambda t: t.replace("<", "‹").replace(">", "›")  # YouTube rejects < and >
    return {
        "snippet": {"title": clean(row["title"])[:100], "description": clean(row["description"])[:4900],
                    "tags": [t.strip() for t in row["tags"].split(",") if t.strip()],
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
    auth = {"Authorization": f"Bearer {token}"}
    for attempt in range(4):
        try:
            with open(path, "rb") as f:
                resp = requests.put(location, data=f, timeout=900,
                                    headers={**auth, "Content-Type": "video/mp4", "Content-Length": str(size)})
            if resp.ok:
                return resp.json()
            print(f"  upload attempt {attempt + 1} failed ({resp.status_code}): {resp.text[:200]}", flush=True)
        except requests.RequestException as e:
            print(f"  upload attempt {attempt + 1} broke ({type(e).__name__})", flush=True)
        time.sleep(20)
        try:  # did YouTube get it all anyway? then use that video (no duplicate)
            st = requests.put(location, headers={**auth, "Content-Range": f"bytes */{size}", "Content-Length": "0"},
                              timeout=60)
            if st.status_code in (200, 201):
                return st.json()
        except requests.RequestException:
            pass
    sys.exit("YouTube upload failed")


def set_thumbnail(token, vid, media, pid):
    """Custom cover from Cloudinary insta/thumbnails/<id>.jpg (shared with Instagram). Never fails the upload."""
    try:
        img = requests.get(f"{media}/image/upload/insta/thumbnails/{pid}.jpg", timeout=60)
        if not img.ok:
            print(f"No thumbnail on Cloudinary for {pid} ({img.status_code}): YouTube picks a frame")
            return
        r = requests.post("https://www.googleapis.com/upload/youtube/v3/thumbnails/set",
                          params={"videoId": vid, "uploadType": "media"}, data=img.content, timeout=120,
                          headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"})
        print(f"Thumbnail: {'set' if r.ok else f'failed ({r.status_code}) {r.text[:200]}'}")
    except requests.RequestException as e:
        print(f"Thumbnail failed: {e}")


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
    """insta/reel/<id>.mp4 and insta/thumbnails/<id>.jpg are shared with the Instagram loop:
    delete them only once the reel is posted on both."""
    key, secret = os.environ.get("CLOUDINARY_API_KEY"), os.environ.get("CLOUDINARY_API_SECRET")
    ids = posted_on_both()
    if not (key and secret and ids):
        print("Nothing to delete from Cloudinary (not posted on Instagram yet, or keys missing)")
        return
    cloud = media.rstrip("/").rsplit("/", 1)[-1]
    for rtype, folder in (("video", "insta/reel"), ("image", "insta/thumbnails")):
        try:
            resp = requests.delete(f"https://api.cloudinary.com/v1_1/{cloud}/resources/{rtype}/upload",
                                   params=[("public_ids[]", f"{folder}/{i}") for i in ids],
                                   auth=(key, secret), timeout=60)
            gone = [i for i, v in resp.json().get("deleted", {}).items() if v == "deleted"]
            print(f"Deleted from Cloudinary (posted on both): {gone}")
        except Exception as e:  # noqa: BLE001 - never fail an upload over cleanup
            print(f"Warning: could not delete from Cloudinary ({folder}): {e}")


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
    pid = item["id"]
    meta = metadata(pid, item)
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
    set_thumbnail(token, vid, media, pid)
    print(f"Uploaded {pid}: https://youtube.com/shorts/{vid}  "
          f"(privacy: {video.get('status', {}).get('privacyStatus')}, "
          f"upload: {video.get('status', {}).get('uploadStatus')})")
    delete_from_cloudinary(media)


if __name__ == "__main__":
    main()
