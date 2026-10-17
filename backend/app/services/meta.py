"""Meta Graph API: Instagram (Business Discovery — any Business/Creator account) and Facebook Pages (managed pages only)."""
import re
import time
from urllib.parse import urlencode

import httpx

from ..core.lib import ApiError
from .youtube import _num, title_from

GRAPH = "https://graph.facebook.com/v23.0"
DIALOG = "https://www.facebook.com/v23.0/dialog/oauth"
# read analytics + read/reply comments on the Page and its Instagram
SCOPES = ("pages_show_list,pages_read_engagement,pages_read_user_content,pages_manage_engagement,"
          "instagram_basic,instagram_manage_insights,instagram_manage_comments,business_management")


def graph_get(path: str, params: dict) -> dict:
    url = path if path.startswith("http") else f"{GRAPH}/{path}"
    r = httpx.get(url, params=params, timeout=30)
    data = r.json()
    if r.status_code >= 400 or data.get("error"):
        raise ApiError(f"Meta: {data.get('error', {}).get('message', r.reason_phrase)}")
    return data


def graph_post(path: str, data: dict) -> dict:
    r = httpx.post(f"{GRAPH}/{path}", data=data, timeout=30)
    body = r.json()
    if r.status_code >= 400 or body.get("error"):
        raise ApiError(f"Meta: {body.get('error', {}).get('message', r.reason_phrase)}")
    return body


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


# ---------------- single post + comments (Page token) ----------------

def _when(ts: str | None) -> str:
    return (ts or "")[:16].replace("T", " ")


def fb_post(post_id: str, token: str) -> dict:
    p = graph_get(post_id, {"fields": "message,story,created_time,permalink_url,full_picture,status_type,shares,"
                                      "attachments{media_type,media,url,subattachments{media_type,media,url}},"
                                      "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)",
                            "access_token": token})
    media = []
    for a in (p.get("attachments") or {}).get("data", []):
        subs = (a.get("subattachments") or {}).get("data") or [a]
        for s_ in subs:
            img = ((s_.get("media") or {}).get("image") or {}).get("src")
            video = (s_.get("media") or {}).get("source")
            if video:
                media.append({"type": "video", "url": video, "thumbnail": img})
            elif img:
                media.append({"type": "image", "url": img})
    if not media and p.get("full_picture"):
        media.append({"type": "image", "url": p["full_picture"]})
    return {"text": p.get("message") or p.get("story") or "", "publishedAt": (p.get("created_time") or "")[:10], "url": p.get("permalink_url"),
            "media": media, "likes": _num((p.get("reactions") or {}).get("summary", {}).get("total_count")),
            "comments": _num((p.get("comments") or {}).get("summary", {}).get("total_count")),
            "shares": _num((p.get("shares") or {}).get("count")), "views": 0}


def _fb_comment(c: dict) -> dict:
    who = c.get("from") or {}
    return {"id": c["id"], "author": who.get("name") or "Facebook user",
            "authorImage": ((who.get("picture") or {}).get("data") or {}).get("url"),
            "text": c.get("message") or "", "likes": _num(c.get("like_count")), "publishedAt": _when(c.get("created_time")),
            "replyCount": _num(c.get("comment_count")), "replies": []}


FB_C_FIELDS = "id,from{name,picture},message,created_time,like_count,comment_count"


def fb_comments(post_id: str, token: str, after: str | None = None, order: str = "relevance") -> dict:
    params = {"fields": FB_C_FIELDS, "filter": "toplevel", "limit": "50", "access_token": token}
    if order == "time":  # newest first; default ("Top") lets Facebook choose its own order
        params["order"] = "reverse_chronological"
    if after:
        params["after"] = after
    data = graph_get(f"{post_id}/comments", params)
    nxt = (data.get("paging") or {}).get("cursors", {}).get("after") if (data.get("paging") or {}).get("next") else None
    return {"items": [_fb_comment(c) for c in data.get("data", [])], "nextPageToken": nxt, "disabled": False}


def fb_replies(comment_id: str, token: str) -> list[dict]:
    data = graph_get(f"{comment_id}/comments", {"fields": FB_C_FIELDS, "limit": "100", "access_token": token})
    return [_fb_comment(c) for c in data.get("data", [])]


def fb_write(target_id: str, text: str, token: str) -> dict:
    """Comment on a post (target = post id) or reply to a comment (target = comment id), as the Page."""
    new_id = graph_post(f"{target_id}/comments", {"message": text, "access_token": token})["id"]
    try:
        return _fb_comment(graph_get(new_id, {"fields": FB_C_FIELDS, "access_token": token}))
    except ApiError:
        return {"id": new_id, "author": "Aapka Page", "text": text, "likes": 0, "publishedAt": "abhi", "replyCount": 0, "replies": []}


def ig_media(media_id: str, token: str) -> dict:
    m = graph_get(media_id, {"fields": "caption,media_type,media_product_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count,"
                                       "children{media_type,media_url,thumbnail_url}", "access_token": token})

    def one(x: dict) -> dict:
        return {"type": "video" if x.get("media_type") == "VIDEO" else "image", "url": x.get("media_url"), "thumbnail": x.get("thumbnail_url")}

    kids = (m.get("children") or {}).get("data") or []
    return {"text": m.get("caption") or "", "publishedAt": (m.get("timestamp") or "")[:10], "url": m.get("permalink"),
            "media": [one(k) for k in kids] if kids else ([one(m)] if m.get("media_url") else []),
            "likes": _num(m.get("like_count")), "comments": _num(m.get("comments_count")), "shares": 0, "views": 0}


def _ig_comment(c: dict) -> dict:
    replies = [_ig_comment(r) for r in (c.get("replies") or {}).get("data", [])]
    return {"id": c["id"], "author": c.get("username") or "instagram user", "authorImage": None, "text": c.get("text") or "",
            "likes": _num(c.get("like_count")), "publishedAt": _when(c.get("timestamp")), "replyCount": len(replies), "replies": replies}


IG_C_FIELDS = "id,text,username,timestamp,like_count"


def ig_comments(media_id: str, token: str, after: str | None = None) -> dict:
    params = {"fields": f"{IG_C_FIELDS},replies{{{IG_C_FIELDS}}}", "limit": "50", "access_token": token}
    if after:
        params["after"] = after
    data = graph_get(f"{media_id}/comments", params)
    nxt = (data.get("paging") or {}).get("cursors", {}).get("after") if (data.get("paging") or {}).get("next") else None
    return {"items": [_ig_comment(c) for c in data.get("data", [])], "nextPageToken": nxt, "disabled": False}


def ig_replies(comment_id: str, token: str) -> list[dict]:
    data = graph_get(f"{comment_id}/replies", {"fields": IG_C_FIELDS, "limit": "100", "access_token": token})
    return [_ig_comment(c) for c in data.get("data", [])]


def ig_write(media_id: str, parent_id: str | None, text: str, token: str) -> dict:
    """New comment on own media, or reply to a comment, as the Instagram account."""
    path = f"{parent_id}/replies" if parent_id else f"{media_id}/comments"
    new_id = graph_post(path, {"message": text, "access_token": token})["id"]
    try:
        return _ig_comment(graph_get(new_id, {"fields": IG_C_FIELDS, "access_token": token}))
    except ApiError:
        return {"id": new_id, "author": "aap", "text": text, "likes": 0, "publishedAt": "abhi", "replyCount": 0, "replies": []}
