"""
One-time, on your Mac: get the YouTube refresh token.

    python3 test_y_30sec/yt/get_token.py ~/Downloads/client_secret_XXXX.json
    (or: python3 test_y_30sec/yt/get_token.py CLIENT_ID CLIENT_SECRET)

A browser opens -> pick the Google account that owns the YouTube channel -> Allow.
(If Google shows "app isn't verified": Advanced -> Go to ... (unsafe). It is your own app.)
The refresh token is saved to in_up/.env as YT_REFRESH_TOKEN (not printed).
Copy it from there into the GitHub secret YT_REFRESH_TOKEN.
Needs an OAuth client of type "Desktop app". With the app "In production" the token does not expire.
"""

import http.server
import json
import os
import sys
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
PORT = 8765
ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env")


def client_from_args():
    if len(sys.argv) == 2:
        data = json.load(open(os.path.expanduser(sys.argv[1]), encoding="utf-8"))
        data = data.get("installed") or data.get("web") or data
        return data["client_id"], data["client_secret"]
    if len(sys.argv) == 3:
        return sys.argv[1], sys.argv[2]
    sys.exit(__doc__)


def save_env(key, value):
    path = os.path.abspath(ENV)
    lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
    lines = [l for l in lines if not l.startswith(f"{key}=")] + [f"{key}={value}"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def main():
    cid, secret = client_from_args()
    redirect = f"http://127.0.0.1:{PORT}/"
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent"})
    got = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Done. You can close this tab and go back to the terminal.</h2>")

        def log_message(self, *a):
            pass

    print("Opening the browser... if it does not open, paste this URL:\n" + url)
    webbrowser.open(url)
    srv = http.server.HTTPServer(("127.0.0.1", PORT), Handler)
    while "code" not in got and "error" not in got:
        srv.handle_request()
    if "error" in got:
        sys.exit(f"Google said: {got['error']}")
    data = urllib.parse.urlencode({"code": got["code"], "client_id": cid, "client_secret": secret,
                                   "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    tok = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", data))
    if "refresh_token" not in tok:
        sys.exit("No refresh token returned. Remove the app's access at myaccount.google.com/permissions and run again.")
    path = save_env("YT_REFRESH_TOKEN", tok["refresh_token"])
    print(f"\nSaved YT_REFRESH_TOKEN to {path}")
    print("Now copy that line's value into the GitHub secret YT_REFRESH_TOKEN.")


if __name__ == "__main__":
    main()
