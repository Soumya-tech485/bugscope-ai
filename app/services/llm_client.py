from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

import httpx


class LLMError(Exception):
    pass


def parse_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()

    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass

    return {"raw": text}


class LLMClient:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (
            base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        ).rstrip("/")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def fallback_json(self) -> Dict[str, Any]:
        return {
            "root_cause": "LLM API key is not configured. Heuristic localization only.",
            "confidence": 0.2,
            "fix_plan": "Set OPENAI_API_KEY to enable AI root-cause analysis.",
            "replacement_code": "",
            "explanation": "No LLM key found.",
            "raw": "fallback",
        }

    def chat_json(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        max_tokens: int = 1200,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return self.fallback_json()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }

        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=90,
        )

        response.raise_for_status()
        data = response.json()

        content = data["choices"][0]["message"]["content"]
        return parse_json(content)