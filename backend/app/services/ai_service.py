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

# Google retires Gemini models regularly. Besides the configured model we ask the API which "flash" models exist
# (cached for a day) and follow the replacement Google names in a 404 — so nobody has to update code or settings.
_models_cache: dict = {"at": 0.0, "names": []}


def _version(name: str) -> tuple:
    nums = re.findall(r"\d+(?:\.\d+)?", name)
    return tuple(float(n) for n in nums[:1]) or (0.0,)


def _discover_models(key: str) -> list[str]:
    if time.time() - _models_cache["at"] < 86400 and _models_cache["names"]:
        return _models_cache["names"]
    try:
        r = httpx.get("https://generativelanguage.googleapis.com/v1beta/models", params={"pageSize": "200"},
                      headers={"x-goog-api-key": key}, timeout=20)
        items = r.json().get("models", []) if r.status_code == 200 else []
    except (httpx.HTTPError, ValueError):
        items = []
    names = []
    for m in items:
        n = m.get("name", "").removeprefix("models/")
        if ("generateContent" in (m.get("supportedGenerationMethods") or []) and "flash" in n
                and not any(x in n for x in ("image", "tts", "audio", "live", "embedding", "thinking", "exp"))):
            names.append(n)
    # newest version first; stable before preview; full flash before lite
    names.sort(key=lambda n: (_version(n), "preview" not in n, "lite" not in n), reverse=True)
    if names:
        _models_cache.update(at=time.time(), names=names)
    return names


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
    models = list(dict.fromkeys([m for m in [_models_cache["names"][0] if _models_cache["names"] else None, settings.GEMINI_MODEL] if m]))
    last = "AI service abhi busy hai"
    discovered = False
    started = time.time()
    i = 0
    while i < len(models) and i < 6:
        model = models[i]
        i += 1
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = httpx.post(url, headers={"x-goog-api-key": key}, timeout=httpx.Timeout(45, connect=10), json=body)
        except httpx.HTTPError as e:
            log.warning("gemini %s network error: %s", model, type(e).__name__)
            last = "AI se connect nahi ho paya"
            if not discovered:  # slow / unreachable model → try lighter ones too
                discovered = True
                models += [m for m in sorted(_discover_models(key), key=lambda n: "lite" not in n) if m not in models]
            if time.time() - started > 75:
                break
            continue
        if r.status_code == 200:
            data = r.json()
            parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            if text.strip():
                if model != settings.GEMINI_MODEL and not (_models_cache["names"] and _models_cache["names"][0] == model):
                    _models_cache["names"] = [model, *[n for n in _models_cache["names"] if n != model]]
                    _models_cache["at"] = time.time()
                return text
            last = "AI ne khaali jawab diya (safety filter)"
            continue
        msg = _gemini_error(r)
        log.warning("gemini %s failed %s: %s", model, r.status_code, msg[:200])
        if r.status_code in (400, 401, 403) and "model" not in msg.lower():
            # key / API problem — other models won't help
            raise ApiError(f"Gemini key mein dikkat: {msg[:160].rstrip('.')}. Render → GEMINI_API_KEY check karein.")
        suggested = re.findall(r"models/([\w.\-]+?)(?=[\s,]|\.(?:\s|$)|$)", msg)
        for name in suggested:
            if name != model and name not in models:
                models.insert(i, name)
        if r.status_code in (404, 429, 500, 503) and not discovered:
            discovered = True
            _models_cache["at"] = 0.0
            found = _discover_models(key)
            if r.status_code != 404:  # overloaded / rate-limited → prefer the light models next
                found = sorted(found, key=lambda n: "lite" not in n)
            models += [m for m in found if m not in models]
        last = "AI ki free limit abhi poori ho gayi, 1 minute baad try karein" if r.status_code == 429 else f"AI busy ({r.status_code})"
        if time.time() - started > 75:
            break
    raise ApiError(f"{last}. Thodi der baad dobara try karein.")


def _chat_compatible(name: str, url: str, key: str | None, model: str, prompt: str, temperature: float,
                     extra_headers: dict | None = None) -> str:
    """OpenAI-style chat API (OpenAI, Groq, OpenRouter)."""
    if not key:
        raise ApiError(f"{name} key set nahi hai.")
    r = httpx.post(url, timeout=httpx.Timeout(45, connect=10),
                   headers={"Authorization": f"Bearer {key.strip()}", **(extra_headers or {})},
                   json={"model": model, "temperature": temperature,
                         "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {}).get("message") or r.reason_phrase
        except ValueError:
            msg = r.reason_phrase
        raise ApiError(f"{name}: {str(msg)[:160]}")
    return r.json()["choices"][0]["message"]["content"] or ""


def _openai(prompt: str, temperature: float) -> str:
    return _chat_compatible("OpenAI", "https://api.openai.com/v1/chat/completions", settings.OPENAI_API_KEY,
                            settings.OPENAI_MODEL, prompt, temperature)


def _groq(prompt: str, temperature: float) -> str:
    return _chat_compatible("Groq", "https://api.groq.com/openai/v1/chat/completions", settings.GROQ_API_KEY,
                            settings.GROQ_MODEL, prompt, temperature)


def _openrouter(prompt: str, temperature: float) -> str:
    return _chat_compatible("OpenRouter", "https://openrouter.ai/api/v1/chat/completions", settings.OPENROUTER_API_KEY,
                            settings.OPENROUTER_MODEL, prompt, temperature,
                            {"HTTP-Referer": settings.FRONTEND_URL, "X-Title": "SocialGrow AI"})


def _anthropic(prompt: str, temperature: float) -> str:
    if not settings.ANTHROPIC_API_KEY:
        raise ApiError("Anthropic key set nahi hai.")
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=httpx.Timeout(45, connect=10),
                   headers={"x-api-key": settings.ANTHROPIC_API_KEY.strip(), "anthropic-version": "2023-06-01"},
                   json={"model": settings.ANTHROPIC_MODEL, "max_tokens": 2000, "temperature": temperature, "system": SYSTEM,
                         "messages": [{"role": "user", "content": prompt}]})
    if r.status_code >= 400:
        raise ApiError(f"Anthropic: {r.reason_phrase}")
    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")


PROVIDERS = {"gemini": (_gemini, "GEMINI_API_KEY"), "groq": (_groq, "GROQ_API_KEY"), "openrouter": (_openrouter, "OPENROUTER_API_KEY"),
             "openai": (_openai, "OPENAI_API_KEY"), "anthropic": (_anthropic, "ANTHROPIC_API_KEY")}


def provider_chain() -> list[str]:
    """The chosen provider first, then every other provider that has a key — so one AI being down never stops the app."""
    first = settings.AI_PROVIDER if settings.AI_PROVIDER in PROVIDERS else "gemini"
    rest = [n for n in PROVIDERS if n != first and getattr(settings, PROVIDERS[n][1], None)]
    return [first, *rest]


def llm(prompt: str, temperature: float = 0.5) -> str:
    errors = []
    for name in provider_chain():
        fn, _ = PROVIDERS[name]
        try:
            text = fn(prompt, temperature)
        except ApiError as e:
            log.warning("llm %s failed: %s", name, str(e.detail)[:200])
            errors.append(str(e.detail))
            continue
        except Exception as e:  # network / unexpected provider error
            log.warning("llm %s error: %s", name, type(e).__name__)
            errors.append(f"{name} se connect nahi ho paya")
            continue
        if text and text.strip():
            return text.strip()
        errors.append(f"{name} ne khaali jawab diya")
    if len(errors) == 1:
        raise ApiError(errors[0])
    raise ApiError("Koi bhi AI abhi jawab nahi de paya — 1-2 minute baad dobara try karein.")


def parse_json(text: str):
    cleaned = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.I)
    cleaned = re.sub(r"```$", "", cleaned).strip()
    start = min([i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0], default=0)
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    return json.loads(cleaned[start : end + 1])
