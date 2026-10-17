"""YouTube Data API v3 — any public channel with the owner's free API key, or own channels via Google OAuth."""
import re

import httpx

from ..core.lib import ApiError


def _num(x) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def title_from(text: str | None, fallback: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t:
        return fallback
    return t[:67] + "…" if len(t) > 70 else t


def parse_input(s: str) -> dict:
    s = s.strip()
    vid = re.search(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/)([\w-]{11})", s)
    if vid:
        return {"videoId": vid.group(1)}
    ch = re.search(r"channel/(UC[\w-]{20,})", s)
    if ch:
        return {"id": ch.group(1)}
    if re.fullmatch(r"UC[\w-]{20,}", s):
        return {"id": s}
    h = re.search(r"@([\w.-]+)", s)
    if h:
        return {"handle": h.group(1)}
    return {"handle": re.sub(r"/.*$", "", re.sub(r"^.*youtube\.com/", "", s))}


def _duration_seconds(d: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    return _num(m.group(1)) * 3600 + _num(m.group(2)) * 60 + _num(m.group(3))


def _yt(path: str, params: dict, key: str) -> dict:
    """`key` is an API key, or "oauth:<access token>" for a channel connected with "Connect with Google"."""
    if key.startswith("oauth:"):
        r = httpx.get(f"https://www.googleapis.com/youtube/v3/{path}", params=params,
                      headers={"Authorization": f"Bearer {key[6:]}"}, timeout=30)
    else:
        r = httpx.get(f"https://www.googleapis.com/youtube/v3/{path}", params={**params, "key": key}, timeout=30)
    data = r.json()
    if r.status_code >= 400 or data.get("error"):
        raise ApiError(f"YouTube: {data.get('error', {}).get('message', r.reason_phrase)}")
    return data


def fetch_youtube(raw: str, key: str) -> dict:
    target = parse_input(raw)
    if target.get("videoId"):
        vr = _yt("videos", {"part": "snippet", "id": target["videoId"]}, key)
        items = vr.get("items") or []
        if not items:
            raise ApiError("Is video link ka channel nahi mila.")
        target = {"id": items[0]["snippet"]["channelId"]}
    params = {"part": "snippet,statistics,contentDetails"}
    params.update({"id": target["id"]} if target.get("id") else {"forHandle": target.get("handle") or raw})
    ch = (_yt("channels", params, key).get("items") or [None])[0]
    if not ch:
        raise ApiError("YouTube channel nahi mila. Handle (@name) ya channel URL check karein.")
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids = [i["contentDetails"]["videoId"] for i in _yt("playlistItems", {"part": "contentDetails", "playlistId": uploads, "maxResults": "50"}, key).get("items", [])]
    posts = []
    if ids:
        for v in _yt("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids)}, key).get("items", []):
            secs = _duration_seconds(v["contentDetails"].get("duration", ""))
            st = v.get("statistics", {})
            posts.append({
                "externalId": v["id"], "title": title_from(v["snippet"]["title"], "YouTube video"),
                "format": "Short" if 0 < secs <= 180 else "Video", "publishedAt": v["snippet"]["publishedAt"][:10],
                "views": _num(st.get("viewCount")), "likes": _num(st.get("likeCount")), "comments": _num(st.get("commentCount")),
                "shares": 0, "url": f"https://www.youtube.com/watch?v={v['id']}",
            })
    stats = ch.get("statistics", {})
    return {
        "externalId": ch["id"],
        "username": (ch["snippet"].get("customUrl") or ch["snippet"]["title"]).lstrip("@"),
        "displayName": ch["snippet"]["title"],
        "followers": _num(stats.get("subscriberCount")),
        "following": 0,
        "totalViews": _num(stats.get("viewCount")),
        "posts": posts,
    }


def _comment(c: dict, cid: str) -> dict:
    sn = c["snippet"]
    return {"id": cid, "author": sn.get("authorDisplayName"), "authorImage": sn.get("authorProfileImageUrl"),
            "authorChannelUrl": sn.get("authorChannelUrl"), "text": sn.get("textOriginal") or sn.get("textDisplay") or "",
            "likes": _num(sn.get("likeCount")), "publishedAt": (sn.get("publishedAt") or "")[:16].replace("T", " ")}


def fetch_comments(video_id: str, key: str, page_token: str | None = None, order: str = "relevance") -> dict:
    """One page (up to 50) of comment threads with the first replies. Read-only."""
    params = {"part": "snippet,replies", "videoId": video_id, "maxResults": "50", "order": order if order in ("relevance", "time") else "relevance",
              "textFormat": "plainText"}
    if page_token:
        params["pageToken"] = page_token
    try:
        data = _yt("commentThreads", params, key)
    except ApiError as e:
        if "disabled comments" in str(e.detail).lower():
            return {"items": [], "nextPageToken": None, "disabled": True}
        raise
    items = []
    for t in data.get("items", []):
        top = t["snippet"]["topLevelComment"]
        items.append({**_comment(top, top["id"]), "threadId": t["id"], "replyCount": _num(t["snippet"].get("totalReplyCount")),
                      "replies": [_comment(r, r["id"]) for r in (t.get("replies") or {}).get("comments", [])][::-1]})
    return {"items": items, "nextPageToken": data.get("nextPageToken"), "disabled": False}


def fetch_replies(parent_id: str, key: str) -> list[dict]:
    data = _yt("comments", {"part": "snippet", "parentId": parent_id, "maxResults": "100", "textFormat": "plainText"}, key)
    return [_comment(c, c["id"]) for c in data.get("items", [])]


def fetch_video(video_id: str, key: str) -> dict:
    items = _yt("videos", {"part": "snippet,statistics,contentDetails", "id": video_id}, key).get("items") or []
    if not items:
        raise ApiError("Video nahi mili (shayad delete ya private ho gayi).")
    v = items[0]
    st = v.get("statistics", {})
    return {"id": v["id"], "title": v["snippet"]["title"], "description": v["snippet"].get("description", ""),
            "publishedAt": v["snippet"]["publishedAt"][:10], "channelTitle": v["snippet"].get("channelTitle"),
            "thumbnail": ((v["snippet"].get("thumbnails") or {}).get("high") or {}).get("url"),
            "views": _num(st.get("viewCount")), "likes": _num(st.get("likeCount")), "comments": _num(st.get("commentCount")),
            "durationSeconds": _duration_seconds(v["contentDetails"].get("duration", "")),
            "url": f"https://www.youtube.com/watch?v={v['id']}"}


def _post(path: str, body: dict, token: str) -> dict:
    r = httpx.post(f"https://www.googleapis.com/youtube/v3/{path}", params={"part": "snippet"}, json=body,
                   headers={"Authorization": f"Bearer {token}"}, timeout=30)
    data = r.json()
    if r.status_code >= 400 or data.get("error"):
        raise ApiError(f"YouTube: {data.get('error', {}).get('message', r.reason_phrase)}")
    return data


def post_reply(parent_id: str, text: str, token: str) -> dict:
    """Reply to a comment as the connected channel."""
    c = _post("comments", {"snippet": {"parentId": parent_id, "textOriginal": text}}, token)
    return _comment(c, c["id"])


def post_comment(video_id: str, text: str, token: str) -> dict:
    """New top-level comment on a video as the connected channel."""
    t = _post("commentThreads", {"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}}, token)
    top = t["snippet"]["topLevelComment"]
    return {**_comment(top, top["id"]), "threadId": t["id"], "replyCount": 0, "replies": []}
