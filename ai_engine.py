"""AI provider integration: local Ollama inference, or BYOK (Bring Your Own Key) hosted models.

No third-party HTTP client is required — both providers are reached via urllib from the
standard library, so this module works without extra dependencies (important for local-only
deployments that may not have internet access to install packages).
"""

import json
import urllib.error
import urllib.request

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_BYOK_BASE_URL = "https://api.openai.com/v1"
DEFAULT_BYOK_MODEL = "gpt-4o-mini"

REQUEST_TIMEOUT_SECONDS = 60


def _post_json(url, payload, headers=None, timeout=REQUEST_TIMEOUT_SECONDS):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def ollama_status(host=None):
    """Check whether a local Ollama server is reachable, and list installed models.

    Returns (is_running, models, error_message).
    """
    host = (host or DEFAULT_OLLAMA_HOST).rstrip("/")
    try:
        data = _get_json(f"{host}/api/tags")
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return True, models, None
    except urllib.error.URLError as exc:
        return False, [], str(exc.reason if hasattr(exc, "reason") else exc)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a status message
        return False, [], str(exc)


def chat_with_ollama(messages, host=None, model=None):
    host = (host or DEFAULT_OLLAMA_HOST).rstrip("/")
    model = model or DEFAULT_OLLAMA_MODEL
    payload = {"model": model, "messages": messages, "stream": False}
    try:
        data = _post_json(f"{host}/api/chat", payload)
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        return None, (
            f"Could not reach Ollama at {host} ({reason}). "
            "Make sure Ollama is installed and running (`ollama serve`)."
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"Ollama request failed: {exc}"

    if "error" in data:
        error = data["error"]
        if "not found" in error.lower():
            return None, (
                f"Model '{model}' is not installed in Ollama. "
                f"Run `ollama pull {model}` and try again."
            )
        return None, f"Ollama error: {error}"

    content = (data.get("message") or {}).get("content")
    if not content:
        return None, "Ollama returned an empty response."
    return content.strip(), None


def chat_with_byok(messages, base_url=None, api_key=None, model=None):
    base_url = (base_url or DEFAULT_BYOK_BASE_URL).rstrip("/")
    model = model or DEFAULT_BYOK_MODEL
    if not api_key:
        return None, "No API key configured for the hosted AI provider."

    payload = {"model": model, "messages": messages}
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        data = _post_json(f"{base_url}/chat/completions", payload, headers=headers)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return None, f"AI provider returned HTTP {exc.code}: {body[:300]}"
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        return None, f"Could not reach AI provider at {base_url} ({reason})."
    except Exception as exc:  # noqa: BLE001
        return None, f"AI provider request failed: {exc}"

    try:
        return data["choices"][0]["message"]["content"].strip(), None
    except (KeyError, IndexError, TypeError):
        return None, "AI provider returned an unexpected response format."


def get_chat_reply(settings, messages):
    """Dispatch to the configured provider.

    `settings` is an AISettings row (or None for defaults). `messages` is a list of
    {"role": "system"|"user"|"assistant", "content": str} dicts.
    Returns (reply_text, error_message) — exactly one of which is None.
    """
    provider = settings.provider if settings else "ollama"
    if provider == "byok" and settings and settings.byok_api_key:
        return chat_with_byok(
            messages,
            base_url=settings.byok_base_url,
            api_key=settings.byok_api_key,
            model=settings.byok_model,
        )
    return chat_with_ollama(
        messages,
        host=settings.ollama_host if settings else None,
        model=settings.ollama_model if settings else None,
    )
