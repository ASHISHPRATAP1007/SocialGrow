"""Meta Graph API: Instagram (Business Discovery — any Business/Creator account) and Facebook Pages (managed pages only)."""
import re

import httpx

from ..core.lib import ApiError
from .youtube import _num, title_from

GRAPH = "https://graph.facebook.com/v23.0"


def graph_get(path: str, params: dict) -> dict:
    url = path if path.startswith("http") else f"{GRAPH}/{path}"
    r = httpx.get(url, params=params, timeout=30)
    data = r.json()
    if r.status_code >= 400 or data.get("error"):
        raise ApiError(f"Meta: {data.get('error', {}).get('message', r.reason_phrase)}")
    return data


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


def fetch_facebook(raw: str, token: str) -> dict:
    want = re.sub(r"^@", "", re.sub(r"[/?].*$", "", re.sub(r"^.*facebook\.com/", "", raw.strip()))).lower()
    pages = graph_get("me/accounts", {"fields": "id,name,username,access_token", "limit": "100", "access_token": token}).get("data", [])
    page = next((p for p in pages if p["id"] == want or (p.get("username") or "").lower() == want or p["name"].lower() == want), None)
    if not page:
        names = ", ".join(p["name"] for p in pages) or "koi nahi"
        raise ApiError(f"Ye Page aapke Meta token se managed nahi hai. Available pages: {names}")
    info = graph_get(page["id"], {
        "fields": "name,username,fan_count,followers_count,posts.limit(30){id,message,created_time,permalink_url,shares,"
                  "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)}",
        "access_token": page["access_token"],
    })
    return {
        "externalId": page["id"], "username": info.get("username") or page.get("username") or page["name"], "displayName": info["name"],
        "followers": _num(info.get("followers_count") or info.get("fan_count")), "following": 0,
        "posts": [{
            "externalId": p["id"], "title": title_from(p.get("message"), "Facebook post"), "format": "Post",
            "publishedAt": p["created_time"][:10], "views": 0,
            "likes": _num((p.get("reactions") or {}).get("summary", {}).get("total_count")),
            "comments": _num((p.get("comments") or {}).get("summary", {}).get("total_count")),
            "shares": _num((p.get("shares") or {}).get("count")), "url": p.get("permalink_url"),
        } for p in (info.get("posts") or {}).get("data", [])],
    }
