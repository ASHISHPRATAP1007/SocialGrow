"""Google OAuth for YouTube ("Connect with Google"). Read-only scope; refresh tokens are stored server-side
and turned into short-lived access tokens on every sync, so nobody ever has to re-enter anything."""
from urllib.parse import urlencode

import httpx

from ..core.lib import ApiError

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
# readonly for analytics, force-ssl to reply to comments, upload to publish videos — all from inside SocialGrow
WRITE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
SCOPE = f"https://www.googleapis.com/auth/youtube.readonly {WRITE_SCOPE} {UPLOAD_SCOPE}"


def oauth_url(client_id: str, redirect_uri: str, state: str) -> str:
    return f"{AUTH}?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state,
    })


def _token(data: dict) -> dict:
    r = httpx.post(TOKEN, data=data, timeout=30)
    body = r.json()
    if r.status_code >= 400 or body.get("error"):
        raise ApiError(f"Google: {body.get('error_description') or body.get('error') or r.reason_phrase}")
    return body


def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str) -> dict:
    return _token({"code": code, "client_id": client_id, "client_secret": client_secret,
                   "redirect_uri": redirect_uri, "grant_type": "authorization_code"})


def access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    return _token({"client_id": client_id, "client_secret": client_secret, "refresh_token": refresh_token,
                   "grant_type": "refresh_token"})["access_token"]


def my_channels(token: str) -> list[dict]:
    r = httpx.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "mine": "true", "maxResults": "50"},
                  headers={"Authorization": f"Bearer {token}"}, timeout=30)
    body = r.json()
    if r.status_code >= 400 or body.get("error"):
        raise ApiError(f"YouTube: {body.get('error', {}).get('message', r.reason_phrase)}")
    return [{"id": c["id"], "title": c["snippet"]["title"], "handle": (c["snippet"].get("customUrl") or "").lstrip("@") or None}
            for c in body.get("items", [])]


def start_upload(token: str, meta: dict, size: int, mime: str, origin: str) -> str:
    """Opens a resumable upload session; the browser then sends the file straight to YouTube (not through our server)."""
    r = httpx.post("https://www.googleapis.com/upload/youtube/v3/videos",
                   params={"uploadType": "resumable", "part": "snippet,status"}, json=meta, timeout=30,
                   headers={"Authorization": f"Bearer {token}", "X-Upload-Content-Length": str(size),
                            "X-Upload-Content-Type": mime, "Origin": origin})
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message")
        except ValueError:
            msg = None
        raise ApiError(f"YouTube upload: {msg or r.reason_phrase}")
    url = r.headers.get("location")
    if not url:
        raise ApiError("YouTube ne upload session nahi diya. Thodi der baad try karein.")
    return url
