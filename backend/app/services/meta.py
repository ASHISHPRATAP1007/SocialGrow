"""Meta Graph API: Instagram (Business Discovery — any Business/Creator account) and Facebook Pages (managed pages only)."""
import re
import time
from urllib.parse import urlencode

import httpx

from ..core.lib import ApiError
from .youtube import _num, title_from

GRAPH = "https://graph.facebook.com/v23.0"
DIALOG = "https://www.facebook.com/v23.0/dialog/oauth"
SCOPES = "pages_show_list,pages_read_engagement,instagram_basic,instagram_manage_insights,business_management"


def graph_get(path: str, params: dict) -> dict:
    url = path if path.startswith("http") else f"{GRAPH}/{path}"
    r = httpx.get(url, params=params, timeout=30)
    data = r.json()
    if r.status_code >= 400 or data.get("error"):
        raise ApiError(f"Meta: {data.get('error', {}).get('message', r.reason_phrase)}")
    return data


def oauth_url(app_id: str, redirect_uri: str, state: str) -> str:
    return f"{DIALOG}?{urlencode({'client_id': app_id, 'redirect_uri': redirect_uri, 'state': state, 'scope': SCOPES, 'response_type': 'code'})}"


def exchange_code(app_id: str, app_secret: str, redirect_uri: str, code: str) -> str:
    return graph_get("oauth/access_token", {"client_id": app_id, "client_secret": app_secret, "redirect_uri": redirect_uri, "code": code})["access_token"]


def long_lived(app_id: str, app_secret: str, token: str) -> tuple[str, int]:
    ex = graph_get("oauth/access_token", {"grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": app_secret, "fb_exchange_token": token})
    return ex["access_token"], int(time.time() * 1000) + int(ex.get("expires_in") or 60 * 86400) * 1000


def discover(token: str) -> dict:
    """Pages the token manages, with their own Page tokens (non-expiring when the user token is long-lived)
    and the linked Instagram Business account."""
    pages = graph_get("me/accounts", {"fields": "id,name,username,access_token,instagram_business_account{id,username}",
                                      "limit": "100", "access_token": token}).get("data", [])
    page_tokens = {}
    for p in pages:
        ig = p.get("instagram_business_account") or {}
        page_tokens[p["id"]] = {"name": p["name"], "username": p.get("username"), "token": p.get("access_token"),
                                "igId": ig.get("id"), "igUsername": ig.get("username")}
    with_ig = next((v for v in page_tokens.values() if v["igId"]), None)
    return {"pages": [p["name"] for p in pages], "pageTokens": page_tokens,
            "igId": with_ig["igId"] if with_ig else None, "igUsername": with_ig["igUsername"] if with_ig else None,
            "igToken": with_ig["token"] if with_ig else None}


def fetch_instagram(raw: str, ig_business_id: str, token: str) -> dict:
    username = re.sub(r"^@", "", re.sub(r"[/?].*$", "", re.sub(r"^.*instagram\.com/", "", raw.strip())))
    if not username:
        raise ApiError("Instagram username daalein.")
    fields = (f"business_discovery.username({username}){{id,username,name,followers_count,follows_count,media_count,"
              "media.limit(30){id,caption,media_type,media_product_type,timestamp,like_count,comments_count,permalink}}")
    b = graph_get(ig_business_id, {"fields": fields, "access_token": token}).get("business_discovery")
    if not b:
        raise ApiError("Instagram account nahi mila. Ye Business/Creator account hona chahiye.")

    def fmt(m: dict) -> str:
        if m.get("media_product_type") == "REELS":
            return "Reel"
        return {"CAROUSEL_ALBUM": "Carousel", "VIDEO": "Video"}.get(m.get("media_type"), "Image")

    return {
        "externalId": b["id"], "username": b["username"], "displayName": b.get("name") or b["username"],
        "followers": _num(b.get("followers_count")), "following": _num(b.get("follows_count")),
        "posts": [{
            "externalId": m["id"], "title": title_from(m.get("caption"), f"{fmt(m)} post"), "format": fmt(m),
            "publishedAt": m["timestamp"][:10], "views": 0, "likes": _num(m.get("like_count")),
            "comments": _num(m.get("comments_count")), "shares": 0, "url": m.get("permalink"),
        } for m in (b.get("media") or {}).get("data", [])],
    }


def _find_page(raw: str, page_tokens: dict) -> tuple[str, dict]:
    want = re.sub(r"^@", "", re.sub(r"[/?].*$", "", re.sub(r"^.*facebook\.com/", "", raw.strip()))).lower()
    for pid, p in page_tokens.items():
        if pid == want or (p.get("username") or "").lower() == want or p["name"].lower() == want:
            return pid, p
    names = ", ".join(p["name"] for p in page_tokens.values()) or "koi nahi"
    raise ApiError(f"Ye Page aapke connected Facebook account se managed nahi hai. Available pages: {names}")


POST_FIELDS = ("id,from{id},message,story,created_time,permalink_url,shares,status_type,"
               "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)")


def _page_posts(page_id: str, token: str) -> list[dict]:
    """Page posts. Some (new Pages experience) pages return nothing on /posts, so fall back to
    /published_posts and then /feed (only the page's own entries)."""
    for edge in ("posts", "published_posts", "feed"):
        try:
            data = graph_get(f"{page_id}/{edge}", {"fields": POST_FIELDS, "limit": "50", "access_token": token}).get("data", [])
        except ApiError:
            continue
        own = [p for p in data if (p.get("from") or {}).get("id", page_id) == page_id]
        if own:
            return own
    return []


def fetch_facebook(raw: str, page_tokens: dict) -> dict:
    page_id, page = _find_page(raw, page_tokens)
    info = graph_get(page_id, {"fields": "name,username,fan_count,followers_count", "access_token": page["token"]})
    posts = _page_posts(page_id, page["token"])
    return {
        "externalId": page_id, "username": info.get("username") or page.get("username") or page["name"], "displayName": info["name"],
        "followers": _num(info.get("followers_count") or info.get("fan_count")), "following": 0,
        "posts": [{
            "externalId": p["id"], "title": title_from(p.get("message") or p.get("story"), "Facebook post"),
            "format": {"added_video": "Video", "added_photos": "Image", "shared_story": "Link"}.get(p.get("status_type"), "Post"),
            "publishedAt": p["created_time"][:10], "views": 0,
            "likes": _num((p.get("reactions") or {}).get("summary", {}).get("total_count")),
            "comments": _num((p.get("comments") or {}).get("summary", {}).get("total_count")),
            "shares": _num((p.get("shares") or {}).get("count")), "url": p.get("permalink_url"),
        } for p in posts],
    }
