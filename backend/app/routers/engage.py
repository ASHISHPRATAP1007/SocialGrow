"""Open any live post (YouTube / Facebook / Instagram): media, stats, all comments, replies, reply or comment as the
account, and AI-written reply suggestions. Comments are fetched live from the platform — nothing is stored."""
import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.deps import Workspace, read_ws, require_ws
from ..core.lib import CONTENT_ROLES, ApiError
from ..database import get_db
from ..models import Post, SocialAccount
from ..services import meta, youtube
from ..services.ai_service import llm, parse_json
from ..services.google import WRITE_SCOPE
from ..services.google import access_token as google_access_token
from ..services.sync_service import resolve
from .ai import gate

router = APIRouter(tags=["engage"])

RECONNECT_FB = "Is Page ke comments ke liye Social Accounts → 'Connect with Facebook' se Page dobara jodein (comments wali permission Allow karein)."


def _load(db: Session, ws: Workspace, post_id: str) -> tuple[Post, SocialAccount]:
    p = db.get(Post, post_id)
    if not p or p.agency_id != ws.agency.id:
        raise ApiError("Post nahi mila.", 404)
    a = db.get(SocialAccount, p.account_id)
    if not a or a.mode != "api" or not p.external_id:
        raise ApiError("Ye feature sirf live (connected) accounts ki posts ke liye hai.")
    return p, a


# ---------------- credentials ----------------

def _yt_key(db: Session, a: SocialAccount, write: bool = False, comments: bool = False) -> str:
    """Read: platform API key (public data), else the channel's own Google login. Listing comments with an OAuth token
    needs the force-ssl scope, so a read-only login falls back to the key. Write: own login with the comment scope."""
    integ = resolve(db, a.agency_id)
    own = integ["googleChannels"].get(a.external_id or "")
    has_write = bool(own and WRITE_SCOPE in (own.get("scope") or ""))
    if not write and integ["youtubeApiKey"] and (comments or not own):
        return integ["youtubeApiKey"]
    if own and own.get("refreshToken") and integ["googleApp"] and (write or not comments or has_write):
        if write and not has_write:
            raise ApiError("Reply karne ke liye is channel ko Social Accounts → 'Connect with Google' se ek baar dobara jodein (comment permission ke saath).")
        return "oauth:" + google_access_token(*integ["googleApp"], own["refreshToken"])
    if write:
        raise ApiError("Reply sirf apne channel par ho sakta hai — channel ko 'Connect with Google' se jodein.")
    if integ["youtubeApiKey"]:
        return integ["youtubeApiKey"]
    raise ApiError("YouTube connection available nahi hai.")


def _meta_token(db: Session, a: SocialAccount) -> str:
    pages = resolve(db, a.agency_id)["ownPageTokens"]
    if a.platform == "facebook":
        page = pages.get(a.external_id or "")
    else:
        page = next((p for p in pages.values() if p.get("igId") == a.external_id), None)
    if not page or not page.get("token"):
        raise ApiError(RECONNECT_FB if a.platform == "facebook" else
                       "Is Instagram ke comments ke liye uska linked Facebook Page 'Connect with Facebook' se jodein.")
    return page["token"]


def _can_reply(db: Session, a: SocialAccount) -> tuple[bool, str | None]:
    if a.platform == "youtube":
        own = resolve(db, a.agency_id)["googleChannels"].get(a.external_id or "") or {}
        if own.get("refreshToken") and WRITE_SCOPE in (own.get("scope") or ""):
            return True, None
        return False, ("Reply ke liye Social Accounts se is channel ko Connect with Google se ek baar dobara jodein (comment permission ke saath)."
                       if own.get("refreshToken") else "Ye channel username se juda hai — reply ke liye channel owner 'Connect with Google' se jode.")
    try:
        _meta_token(db, a)
        return True, None
    except ApiError as e:
        return False, str(e.detail)


def _meta_call(fn, *args):
    try:
        return fn(*args)
    except ApiError as e:
        msg = str(e.detail)
        if "permission" in msg.lower() or "(#10)" in msg or "(#200)" in msg:
            raise ApiError(RECONNECT_FB + f" [{msg[:120]}]") from None
        raise


# ---------------- endpoints ----------------

@router.get("/posts/{post_id}/detail")
def post_detail(post_id: str, ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    p, a = _load(db, ws, post_id)
    base = {"postId": p.id, "accountId": a.id, "platform": a.platform, "username": a.username, "format": p.format,
            "title": p.title, "embedId": None, "durationSeconds": None, "channelTitle": a.display_name}
    if a.platform == "youtube":
        v = youtube.fetch_video(p.external_id, _yt_key(db, a))
        d = {**base, "title": v["title"], "text": v["description"], "publishedAt": v["publishedAt"], "url": v["url"],
             "embedId": v["id"], "durationSeconds": v["durationSeconds"], "media": [], "channelTitle": v["channelTitle"],
             "views": v["views"], "likes": v["likes"], "comments": v["comments"], "shares": 0}
    else:
        token = _meta_token(db, a)
        m = _meta_call(meta.fb_post if a.platform == "facebook" else meta.ig_media, p.external_id, token)
        d = {**base, **m}
    can, why = _can_reply(db, a)
    return {**d, "canReply": can, "replyHint": why}


@router.get("/posts/{post_id}/comments")
def post_comments(post_id: str, pageToken: str | None = None, order: str = "relevance",
                  ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    p, a = _load(db, ws, post_id)
    if a.platform == "youtube":
        return youtube.fetch_comments(p.external_id, _yt_key(db, a, comments=True), pageToken, order)
    token = _meta_token(db, a)
    if a.platform == "facebook":
        return _meta_call(meta.fb_comments, p.external_id, token, pageToken, order)
    return _meta_call(meta.ig_comments, p.external_id, token, pageToken)


@router.get("/posts/{post_id}/comments/{comment_id}/replies")
def comment_replies(post_id: str, comment_id: str, ws: Workspace = Depends(read_ws), db: Session = Depends(get_db)):
    p, a = _load(db, ws, post_id)
    if a.platform == "youtube":
        return youtube.fetch_replies(comment_id, _yt_key(db, a, comments=True))
    token = _meta_token(db, a)
    return _meta_call(meta.fb_replies if a.platform == "facebook" else meta.ig_replies, comment_id, token)


class CommentIn(BaseModel):
    text: str
    parentId: str | None = None


@router.post("/posts/{post_id}/comments")
def write_comment(post_id: str, body: CommentIn, ws: Workspace = Depends(require_ws(CONTENT_ROLES)), db: Session = Depends(get_db)):
    """Reply to a comment (parentId) or add a new comment — as the channel / Page / Instagram account."""
    text = body.text.strip()
    if not text:
        raise ApiError("Reply likhein.")
    if len(text) > 2200:
        raise ApiError("Reply bahut lamba hai (max 2200 characters).")
    p, a = _load(db, ws, post_id)
    if a.platform == "youtube":
        token = _yt_key(db, a, write=True)[len("oauth:"):]
        return youtube.post_reply(body.parentId, text, token) if body.parentId else youtube.post_comment(p.external_id, text, token)
    token = _meta_token(db, a)
    if a.platform == "facebook":
        return _meta_call(meta.fb_write, body.parentId or p.external_id, text, token)
    return _meta_call(meta.ig_write, p.external_id, body.parentId, text, token)


class AiReplyIn(BaseModel):
    comment: str
    author: str | None = None
    tone: str = "friendly"  # friendly | professional | funny | short


TONES = {"friendly": "warm and friendly", "professional": "polite and professional", "funny": "light and witty (never rude)",
         "short": "very short (one line)"}


@router.post("/posts/{post_id}/ai-reply")
def ai_reply(post_id: str, body: AiReplyIn, ws: Workspace = Depends(require_ws(CONTENT_ROLES)), db: Session = Depends(get_db)):
    """3 ready-to-send reply options for a comment, in the commenter's language."""
    if not body.comment.strip():
        raise ApiError("Comment khaali hai.")
    p, a = _load(db, ws, post_id)
    gate(db, ws, "reply")
    brand = ws.agency.brand_name or a.display_name or a.username
    prompt = (
        f"You reply to comments for the {a.platform} account \"{brand}\" (@{a.username}).\n"
        f"Post: {json.dumps(p.title)}\n"
        f"Comment by {json.dumps(body.author or 'a follower')}: {json.dumps(body.comment[:1000])}\n\n"
        f"Write 3 different reply options. Tone: {TONES.get(body.tone, TONES['friendly'])}. "
        "Reply in the SAME language and script as the comment (Hindi in Devanagari, Hinglish in Roman Hindi, English in English). "
        "Thank genuine praise, answer questions helpfully, stay calm and kind with complaints and invite them to DM. "
        "Max 2 short sentences each, at most 1 emoji, no hashtags, no links, never promise discounts or prices. "
        'Return ONLY a JSON array of 3 strings.'
    )
    raw = llm(prompt, temperature=0.8)
    try:
        options = [str(x).strip() for x in parse_json(raw) if str(x).strip()]
    except Exception:  # model returned plain text
        options = [line.strip("-•* \"") for line in raw.splitlines() if line.strip()]
    return {"options": options[:3]}
