# The 30 sec developers: YouTube Shorts autopost

Uploads the SQL reel series (SQL001, SQL002, …) to YouTube as Shorts, **4 a day**
(IST 09:00, 13:00, 17:00, 21:00), fully on GitHub Actions.

- Videos: Cloudinary `yt/reel/SQLxxx.mp4`. This copy is kept only for YouTube; the Instagram loop never deletes it.
  Each file is deleted after it goes up on YouTube.
- Captions: the same `sql_reel_posts.csv` the Instagram loop uses, read from the public `yavnish3/test_in_up` repo.
- Progress: `yt/yt_posted.csv`. Never overwrite it.
- New AI reels (SQL082+): the generator in `test_in_up` also uploads a copy to `yt/reel/`.

## One-time setup

1. **Google Cloud** (console.cloud.google.com, use the Google account that owns the channel):
   - Create a project, then enable **YouTube Data API v3**.
   - OAuth consent screen: External. Add yourself as a test user, then click **Publish app** so it is "In production".
     (While the app is in "Testing", refresh tokens expire after 7 days.)
   - Credentials → Create OAuth client ID → **Desktop app**. Copy the client ID and client secret.
2. On the Mac: `python3 yt/get_token.py CLIENT_ID CLIENT_SECRET`. Allow access in the browser, then copy the refresh token.
3. GitHub repo → Settings → Secrets → Actions: add
   `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`, `MEDIA_BASE_URL`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
   (the last three are the same values as in test_in_up).
4. Copy the hand-made reels to Cloudinary (from `in_up/`):
   `.venv/bin/python test_y_30sec/yt/seed_cloudinary.py ~/Documents/Code/web/test_vid_post/output`
5. Actions → **YouTube loop** → Run workflow (set `upload_now: yes` to test one right away).

**Important:** YouTube keeps videos uploaded through the API from an *unverified* API project
**private** until the project passes Google's audit. Apply for it with the "YouTube API Services Audit and Quota Extension" form.
Until then, uploads arrive as private and you can make them public by hand in YouTube Studio.

Optional secret `YT_PRIVACY` = `public` (default) | `unlisted` | `private`.
