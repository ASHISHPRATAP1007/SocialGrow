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
    ids = [i["contentDetails"]["videoId"] for i in _yt("playlistItems", {"part": "contentDetails", "playlistId": uploads, "maxResults": "30"}, key).get("items", [])]
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
