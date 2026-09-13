"""Central LLM client (DeepSeek via OpenRouter) with failure tracking.

All model calls go through here. Failures are recorded and reported in
evaluation/llm_failures.md; callers apply a deterministic fallback.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Optional

import config
from usage import USAGE

MODEL = config.MODEL_ID


class LLMError(RuntimeError):
    pass


FAILURES: list[dict] = []


def _record_failure(kind: str, error: str, detail: str = "") -> None:
    FAILURES.append({"kind": kind, "model": MODEL, "error": error, "detail": detail[:300]})
    print(f"[llm-failure] {kind}: {error}")


def _post(payload: dict) -> dict:
    key = os.environ.get(config.OPENROUTER_API_KEY_ENV, "")
    if not key:
        raise LLMError("OPENROUTER_API_KEY is not set")
    request = urllib.request.Request(
        config.OPENROUTER_URL,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def chat(prompt: str, max_tokens: int = 500, temperature: float = 0.0,
         model: Optional[str] = None, attempts: int = 3) -> str:
    model = model or MODEL
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    response = None
    for attempt in range(1, attempts + 1):
        try:
            response = _post(payload)
            if "error" in response or "choices" not in response:
                raise LLMError(f"provider error: {str(response)[:150]}")
            break
        except Exception as exc:  # noqa: BLE001
            permanent = (isinstance(exc, urllib.error.HTTPError)
                         and exc.code in (400, 401, 402, 403, 404))
            if attempt == attempts or permanent:
                _record_failure("http", f"{type(exc).__name__}: {exc}")
                raise LLMError(str(exc)) from exc
            time.sleep(2.0 * attempt)
    usage = response.get("usage", {}) or {}
    USAGE.record(model, usage.get("prompt_tokens", 0),
                 usage.get("completion_tokens", 0), usage.get("cost", 0.0))
    try:
        return response["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        _record_failure("response", str(exc), json.dumps(response)[:300])
        raise LLMError("malformed response") from exc


def _extract_json(text: str) -> Optional[Any]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    match = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def chat_json(prompt: str, max_tokens: int = 500, retries: int = 3,
              model: Optional[str] = None) -> Any:
    """Call the model and parse JSON, retrying until a valid structure is returned."""
    last_error = "unknown"
    for attempt in range(1, retries + 1):
        content = chat(prompt, max_tokens=max_tokens, model=model)
        parsed = _extract_json(content)
        if parsed is not None:
            return parsed
        last_error = "response did not contain valid JSON"
        _record_failure("parse", f"attempt {attempt}: {last_error}", content[:300])
    raise LLMError(f"invalid JSON after {retries} attempts: {last_error}")


def failures_summary() -> dict:
    by_kind: dict[str, int] = {}
    for failure in FAILURES:
        by_kind[failure["kind"]] = by_kind.get(failure["kind"], 0) + 1
    return {"total": len(FAILURES), "by_kind": by_kind}


def write_failures(path: str) -> None:
    summary = failures_summary()
    lines = ["# LLM Call Failures", "",
             f"- Total failures: {summary['total']}",
             f"- By kind: {summary['by_kind'] or '{}'}", ""]
    if FAILURES:
        lines += ["| kind | model | error | detail |", "|---|---|---|---|"]
        for failure in FAILURES:
            lines.append(f"| {failure['kind']} | {failure['model']} | "
                         f"{failure['error']} | {failure['detail']} |")
    else:
        lines.append("No LLM call failures were observed.")
    lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
