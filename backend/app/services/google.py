"""Google OAuth for YouTube ("Connect with Google"). Read-only scope; refresh tokens are stored server-side
and turned into short-lived access tokens on every sync, so nobody ever has to re-enter anything."""
from urllib.parse import urlencode

import httpx

from ..core.lib import ApiError

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
# readonly for analytics + force-ssl so the agency can reply to comments from inside SocialGrow
SCOPE = "https://www.googleapis.com/auth/youtube.readonly https://www.googleapis.com/auth/youtube.force-ssl"
WRITE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


def oauth_url(client_id: str, redirect_uri: str, state: str) -> str:
    return f"{AUTH}?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent select_account", "include_granted_scopes": "true", "state": state,
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
