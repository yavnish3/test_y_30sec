# The 30 sec developers: YouTube Shorts autopost

Uploads the SQL reel series (SQL001, SQL002, …) to YouTube as Shorts, **4 a day**
(IST 09:00, 13:00, 17:00, 21:00), fully on GitHub Actions.

- Videos: Cloudinary `insta/reel/SQLxxx.mp4`, ONE copy shared with the Instagram loop (test_in_up).
  A video is deleted only once it is posted on both Instagram and YouTube (each loop checks the other's posted CSV).
- Captions: the same `sql_reel_posts.csv` the Instagram loop uses, read from the public `yavnish3/test_in_up` repo.
- Progress: `yt/yt_posted.csv`. Never overwrite it.
- New AI reels (SQL082+): the generator in `test_in_up` uploads them to `insta/reel/`; both loops pick them up.

## One-time setup

1. **Google Cloud** (console.cloud.google.com, use the Google account that owns the channel):
   - Create a project, then enable **YouTube Data API v3**.
   - OAuth consent screen: External. Add yourself as a test user, then click **Publish app** so it is "In production".
     (While the app is in "Testing", refresh tokens expire after 7 days.)
   - Credentials → Create OAuth client ID → **Desktop app** → **Download JSON**.
2. On the Mac (from `in_up/`): `python3 test_y_30sec/yt/get_token.py ~/Downloads/client_secret_XXXX.json`. Allow access; the refresh token is saved to `in_up/.env`.
3. GitHub repo → Settings → Secrets → Actions: add
   `YT_CLIENT_JSON` (paste the whole JSON file), `YT_REFRESH_TOKEN`, `MEDIA_BASE_URL`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
   (the last three are the same values as in test_in_up).
4. Actions → **YouTube loop** → Run workflow (set `upload_now: yes` to test one right away).

**Important:** YouTube keeps videos uploaded through the API from an *unverified* API project
**private** until the project passes Google's audit. Apply for it with the "YouTube API Services Audit and Quota Extension" form.
Until then, uploads arrive as private and you can make them public by hand in YouTube Studio.

Optional secret `YT_PRIVACY` = `public` (default) | `unlisted` | `private`.
