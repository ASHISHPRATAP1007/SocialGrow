"""LLM calls (Gemini free tier by default; OpenAI or Anthropic via AI_PROVIDER). Keys never reach the browser."""
import json
import logging
import re
import time

import httpx

from ..config import settings
from ..core.lib import ApiError

SYSTEM = """You are SocialGrow AI, a senior social-media analyst for agencies in India.
Rules:
- Only use the analytics JSON you are given. Never invent numbers.
- Never suggest buying followers, likes, views, bots, engagement pods or any fake/inauthentic engagement.
- If the data is labelled "demo data", you may analyse it normally (it is sample data for a demo).
- Be concise, practical and specific. Use simple English that Indian business owners understand."""


log = logging.getLogger("socialgrow.ai")

# Free-tier models to try in order: the configured one first, then lighter fallbacks when it is overloaded / unavailable
GEMINI_FALLBACKS = ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash")


def _gemini_error(r: httpx.Response) -> str:
    try:
        return r.json().get("error", {}).get("message") or r.reason_phrase
    except ValueError:
        return r.reason_phrase


def _gemini(prompt: str, temperature: float) -> str:
    key = (settings.GEMINI_API_KEY or "").strip()
    if not key:
        raise ApiError("AI abhi set nahi hai (GEMINI_API_KEY missing). Support se contact karein.")
    body = {"systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature}}
    models = list(dict.fromkeys([settings.GEMINI_MODEL, *GEMINI_FALLBACKS]))
    last = "AI service abhi busy hai"
    for i, model in enumerate(models):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = httpx.post(url, headers={"x-goog-api-key": key}, timeout=60, json=body)
        except httpx.HTTPError as e:
            log.warning("gemini %s network error: %s", model, type(e).__name__)
            last = "AI se connect nahi ho paya"
            continue
        if r.status_code == 200:
            data = r.json()
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            if text.strip():
                return text
            last = "AI ne khaali jawab diya (safety filter)"
            continue
        msg = _gemini_error(r)
        log.warning("gemini %s failed %s: %s", model, r.status_code, msg[:200])
        if r.status_code in (400, 401, 403) and "model" not in msg.lower():
            # key / API problem — other models won't help
            raise ApiError(f"Gemini key mein dikkat: {msg[:160].rstrip('.')}. Render → GEMINI_API_KEY check karein.")
        last = "AI ki free limit abhi poori ho gayi, 1 minute baad try karein" if r.status_code == 429 else f"AI busy ({r.status_code})"
        if r.status_code in (429, 500, 503) and i == 0:
            time.sleep(1.5)
    raise ApiError(f"{last}. Thodi der baad dobara try karein.")


def _openai(prompt: str, temperature: float) -> str:
    if not settings.OPENAI_API_KEY:
        raise ApiError("AI abhi set nahi hai (OPENAI_API_KEY missing).")
    r = httpx.post("https://api.openai.com/v1/chat/completions", timeout=90,
                   headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                   json={"model": settings.OPENAI_MODEL, "temperature": temperature,
                         "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


def _anthropic(prompt: str, temperature: float) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise ApiError("AI abhi set nahi hai (ANTHROPIC_API_KEY missing).")
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=90,
                   headers={"x-api-key": settings.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
                   json={"model": settings.ANTHROPIC_MODEL, "max_tokens": 2000, "temperature": temperature, "system": SYSTEM,
                         "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")


def llm(prompt: str, temperature: float = 0.5) -> str:
    provider = {"openai": _openai, "anthropic": _anthropic}.get(settings.AI_PROVIDER, _gemini)
    try:
        text = provider(prompt, temperature)
    except ApiError:
        raise
    except Exception as e:  # network / provider error
        log.warning("llm provider error: %s", type(e).__name__)
        raise ApiError("AI service abhi busy hai, thodi der baad try karein.") from e
    if not text.strip():
        raise ApiError("AI se response nahi mila, thodi der baad try karein.")
    return text.strip()


def parse_json(text: str):
    cleaned = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.I)
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start = min([i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0], default=0)
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    return json.loads(cleaned[start : end + 1])
