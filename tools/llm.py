"""One interface to several LLM APIs (standard library only).

    reply = call(cfg, system, user)      # -> Reply(text, usage, cost, seconds)

cfg is one entry of mt/models.json:

    {"provider": "anthropic" | "openai" | "gemini" | "mock",
     "model": "<the provider's model id>",
     "price_in": 4.0, "price_out": 20.0,         # US$ per million tokens
     "price_cache_read": 0.4,                     # optional (default price_in / 10)
     "max_tokens": 16000,                         # output limit (thinking included)
     "extra": {...}}                              # merged into the request body

"extra" is how to set provider options this file doesn't know about
(reasoning effort, thinking level, temperature ...): it is merged as is into
the JSON body, so it follows the provider's own API reference.

API keys come from .env in the repository root (KEY=value lines;
git-ignored): CLAUDE_KEY, OPENAI_KEY, GEMINI_KEY. Environment variables of
the same names, or the providers' usual ones (ANTHROPIC_API_KEY,
OPENAI_API_KEY, GEMINI_API_KEY), work too.
"""
import json
import os
import random
import socket
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEYS_FILE = os.path.join(ROOT, ".env")
KEY_VARS = {"anthropic": ("CLAUDE_KEY", "ANTHROPIC_API_KEY"), "openai": ("OPENAI_KEY", "OPENAI_API_KEY"),
            "gemini": ("GEMINI_KEY", "GEMINI_API_KEY")}


class LLMError(Exception):
    """A request that failed for good (bad key, bad parameter, refusal ...)."""


class Reply:
    def __init__(self, text, usage, cost, seconds, raw=None):
        self.text, self.usage, self.cost, self.seconds, self.raw = text, usage, cost, seconds, raw


def _dotenv():
    out = {}
    if os.path.exists(KEYS_FILE):
        for line in open(KEYS_FILE, encoding="utf-8-sig"):
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            k, eq, v = line.partition("=")
            if eq and not k.strip().startswith("#"):
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def api_key(provider):
    env = _dotenv()
    for var in KEY_VARS[provider]:
        v = env.get(var) or os.environ.get(var, "").strip()
        if v:
            return v
    raise LLMError("no API key: add %s=... to %s" % (KEY_VARS[provider][0], KEYS_FILE))


def merge(a, b):
    """Deep merge of dict b into a copy of dict a."""
    out = dict(a)
    for k, v in b.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def cost_of(cfg, usage):
    pin, pout = cfg.get("price_in", 0.0), cfg.get("price_out", 0.0)
    pread = cfg.get("price_cache_read", pin / 10)
    pwrite = cfg.get("price_cache_write", pin * 1.25)
    return (usage.get("input", 0) * pin + usage.get("output", 0) * pout
            + usage.get("cache_read", 0) * pread + usage.get("cache_write", 0) * pwrite) / 1e6


def _post(url, headers, body, timeout):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=dict(headers, **{"content-type": "application/json"}))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# --- providers: (cfg, system, user) -> (text, usage, raw) -------------------
# usage: input (uncached), output (incl. thinking), cache_read, cache_write

def _anthropic(cfg, system, user, timeout):
    body = {"model": cfg["model"], "max_tokens": cfg.get("max_tokens", 16000),
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}]}
    r = _post("https://api.anthropic.com/v1/messages",
              {"x-api-key": api_key("anthropic"), "anthropic-version": "2023-06-01"},
              merge(body, cfg.get("extra", {})), timeout)
    if r.get("stop_reason") == "max_tokens":
        raise LLMError("reply cut off at max_tokens (%s); raise max_tokens" % cfg.get("max_tokens"))
    if r.get("stop_reason") == "refusal":
        raise LLMError("the model refused")
    text = "".join(c.get("text", "") for c in r.get("content", []) if c.get("type") == "text")
    u = r.get("usage", {})
    return text, {"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
                  "cache_read": u.get("cache_read_input_tokens", 0) or 0,
                  "cache_write": u.get("cache_creation_input_tokens", 0) or 0}, r


def _openai(cfg, system, user, timeout):
    body = {"model": cfg["model"], "instructions": system, "input": user,
            "max_output_tokens": cfg.get("max_tokens", 16000)}
    r = _post("https://api.openai.com/v1/responses",
              {"authorization": "Bearer " + api_key("openai")},
              merge(body, cfg.get("extra", {})), timeout)
    if r.get("status") == "incomplete":
        raise LLMError("reply incomplete: %s" % (r.get("incomplete_details") or {}).get("reason"))
    if r.get("error"):
        raise LLMError(str(r["error"]))
    text = "".join(c.get("text", "") for item in r.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if c.get("type") == "output_text")
    u = r.get("usage", {})
    cached = (u.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0
    return text, {"input": u.get("input_tokens", 0) - cached, "output": u.get("output_tokens", 0),
                  "cache_read": cached, "cache_write": 0}, r


def _gemini(cfg, system, user, timeout):
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json",
                                 "maxOutputTokens": cfg.get("max_tokens", 16000)}}
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % cfg["model"]
    r = _post(url, {"x-goog-api-key": api_key("gemini")}, merge(body, cfg.get("extra", {})), timeout)
    if (r.get("promptFeedback") or {}).get("blockReason"):
        raise LLMError("prompt blocked: %s" % r["promptFeedback"]["blockReason"])
    cands = r.get("candidates") or []
    if not cands:
        raise LLMError("no reply: %s" % json.dumps(r)[:300])
    c = cands[0]
    if c.get("finishReason") not in (None, "STOP"):
        raise LLMError("reply stopped: %s" % c.get("finishReason"))
    text = "".join(p.get("text", "") for p in (c.get("content") or {}).get("parts", []) if not p.get("thought"))
    u = r.get("usageMetadata", {})
    cached = u.get("cachedContentTokenCount", 0) or 0
    return text, {"input": u.get("promptTokenCount", 0) - cached,
                  "output": u.get("candidatesTokenCount", 0) + (u.get("thoughtsTokenCount", 0) or 0),
                  "cache_read": cached, "cache_write": 0}, r


def _mock(cfg, system, user, timeout):
    """Offline stand-in for testing the pipeline: answers every line id it is
    asked for with placeholder English (some lines deliberately too long the
    first time, to exercise the repair step)."""
    import re
    req = json.loads(user[user.index('{"'):])
    out = {}
    for key, sc in req["scenes"].items():
        d = out[key] = {}
        for m in sc["messages"]:
            if "fix" in req and not m.get("rewrite"):
                continue
            for l in m["lines"]:
                lid, ja = l[0], l[1]
                codes = "".join(re.findall(r"\{[^}]*\}", ja.replace("{nobreak}", "")))
                tail = "{nobreak}" if ja.endswith("{nobreak}") else (")" if ja.endswith("）") else "")
                long = ("fix" not in req or cfg.get("stubborn")) and int(lid) % 7 == 0
                d[lid] = ("Line %s %s" % (lid, codes) + (" padding" * 8 if long else "")).strip() + tail
    time.sleep(0.05)
    return json.dumps(out), {"input": len(system + user) // 3, "output": len(json.dumps(out)) // 3,
                             "cache_read": 0, "cache_write": 0}, None


PROVIDERS = {"anthropic": _anthropic, "openai": _openai, "gemini": _gemini, "mock": _mock}


def call(cfg, system, user, timeout=600, tries=6, log=print):
    """One request with retries on rate limits, overload and network errors."""
    fn = PROVIDERS[cfg["provider"]]
    delay = 5.0
    for attempt in range(tries):
        t0 = time.time()
        try:
            text, usage, raw = fn(cfg, system, user, timeout)
            return Reply(text, usage, cost_of(cfg, usage), time.time() - t0, raw)
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:800]
            if e.code not in (408, 409, 429, 500, 502, 503, 504, 529) or attempt == tries - 1:
                raise LLMError("HTTP %d: %s" % (e.code, msg))
            wait = float(e.headers.get("retry-after") or 0) or delay
            log("  %s: HTTP %d, retrying in %.0fs" % (cfg["model"], e.code, wait))
        except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as e:
            if attempt == tries - 1:
                raise LLMError("network: %s" % e)
            wait = delay
            log("  %s: %s, retrying in %.0fs" % (cfg["model"], e, wait))
        time.sleep(wait * (0.8 + 0.4 * random.random()))
        delay = min(delay * 2, 120)
