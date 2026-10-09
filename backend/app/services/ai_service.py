"""LLM calls (Gemini free tier by default; OpenAI or Anthropic via AI_PROVIDER). Keys never reach the browser."""
import json
import re

import httpx

from ..config import settings
from ..core.lib import ApiError

SYSTEM = """You are SocialGrow AI, a senior social-media analyst for agencies in India.
Rules:
- Only use the analytics JSON you are given. Never invent numbers.
- Never suggest buying followers, likes, views, bots, engagement pods or any fake/inauthentic engagement.
- If the data is labelled "demo data", you may analyse it normally (it is sample data for a demo).
- Be concise, practical and specific. Use simple English that Indian business owners understand."""


def _gemini(prompt: str, temperature: float) -> str:
    if not settings.GEMINI_API_KEY:
        raise ApiError("AI abhi set nahi hai (GEMINI_API_KEY missing). Support se contact karein.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent"
    r = httpx.post(url, params={"key": settings.GEMINI_API_KEY}, timeout=90, json={
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    })
    if r.status_code == 429:
        raise ApiError("AI ki free limit abhi poori ho gayi, thodi der baad try karein.")
    r.raise_for_status()
    parts = r.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts)


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
