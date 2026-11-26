"""
One-time, on your Mac: get the YouTube refresh token.

    python3 yt/get_token.py CLIENT_ID CLIENT_SECRET

A browser opens -> pick the Google account that owns the YouTube channel -> allow.
(If Google shows "app isn't verified": Advanced -> Go to ... (unsafe). It is your own app.)
The script prints YT_REFRESH_TOKEN: put it in the GitHub secret of that name.
Nothing is saved to disk. Needs an OAuth client of type "Desktop app".
"""

import http.server
import json
import sys
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
PORT = 8765


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    cid, secret = sys.argv[1], sys.argv[2]
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

    print("Opening the browser… if it does not open, paste this URL:\n" + url)
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
        sys.exit(f"No refresh token returned: {tok}")
    print("\nYT_REFRESH_TOKEN =", tok["refresh_token"])


if __name__ == "__main__":
    main()
