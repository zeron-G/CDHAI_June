from __future__ import annotations

import base64
import json
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx

from cdhai_june.config import LLMConfig
from cdhai_june.utils import compact_text


class LLMClient(ABC):
    provider_name = "base"

    @abstractmethod
    def generate(self, *, system: str, prompt: str) -> str:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    provider_name = "mock"

    def generate(self, *, system: str, prompt: str) -> str:
        del system
        return (
            "Local mock LLM draft. This text is generated without a remote model. "
            "Use it to verify the patient-analysis pipeline, then switch to "
            "`codex_oauth` for real hypothesis generation and narrative reports.\n\n"
            f"Prompt brief: {compact_text(prompt, 900)}"
        )


class OpenAICompatibleClient(LLMClient):
    provider_name = "openai_compatible"

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.base_url = config.openai_base_url.rstrip("/")
        self.api_key = config.openai_api_key or os.environ.get("OPENAI_API_KEY", "")

    def generate(self, *, system: str, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI-compatible provider requires CDHAI_OPENAI_API_KEY or OPENAI_API_KEY.")
        payload = {
            "model": self.config.model,
            "instructions": system,
            "input": prompt,
            "temperature": self.config.temperature,
            "max_output_tokens": self.config.max_output_tokens,
            "store": False,
        }
        with httpx.Client(timeout=90) as client:
            response = client.post(
                f"{self.base_url}/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
        response.raise_for_status()
        return _extract_response_text(response.json())


class CodexOAuthClient(LLMClient):
    provider_name = "codex_oauth"

    DEFAULT_BASE_URL = "https://chatgpt.com/backend-api/codex"
    DEFAULT_REFRESH_URL = "https://auth.openai.com/oauth/token"
    DEFAULT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
    REFRESH_BUFFER_SECONDS = 300

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.auth_path = Path(config.codex_auth_path).expanduser() if config.codex_auth_path else _default_codex_auth_path()

    def generate(self, *, system: str, prompt: str) -> str:
        session = self._ensure_fresh_session()
        payload = {
            "model": self.config.model,
            "instructions": system,
            "input": [{"role": "user", "content": prompt}],
            "stream": True,
            "store": False,
        }
        headers = {
            "Authorization": f"Bearer {session['tokens']['access_token']}",
            "ChatGPT-Account-ID": session["tokens"].get("account_id", ""),
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=120) as client:
            response = client.post(f"{self.DEFAULT_BASE_URL}/responses", headers=headers, json=payload)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return _extract_response_text(response.json())
        return _extract_sse_text(response.text)

    def _load_session(self) -> dict[str, Any]:
        if not self.auth_path.exists():
            raise RuntimeError(f"Codex auth file not found: {self.auth_path}")
        payload = json.loads(self.auth_path.read_text(encoding="utf-8"))
        tokens = payload.get("tokens") or {}
        if not str(tokens.get("access_token", "")).strip():
            raise RuntimeError("Codex auth file does not contain an access token.")
        return {
            "auth_mode": payload.get("auth_mode", "unknown"),
            "tokens": tokens,
            "last_refresh": payload.get("last_refresh"),
        }

    def _ensure_fresh_session(self) -> dict[str, Any]:
        session = self._load_session()
        access_token = session["tokens"]["access_token"]
        expiry = _jwt_expiry(access_token)
        if expiry is None or time.time() < expiry - self.REFRESH_BUFFER_SECONDS:
            return session
        return self._refresh_session(session)

    def _refresh_session(self, session: dict[str, Any]) -> dict[str, Any]:
        refresh_token = session["tokens"].get("refresh_token")
        if not refresh_token:
            raise RuntimeError("Codex auth session is expired and has no refresh token.")
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.DEFAULT_CLIENT_ID,
            "scope": "openid profile email offline_access",
        }
        with httpx.Client(timeout=60) as client:
            response = client.post(self.DEFAULT_REFRESH_URL, headers={"Content-Type": "application/json"}, json=payload)
        response.raise_for_status()
        refreshed = response.json()
        if not refreshed.get("access_token"):
            raise RuntimeError("Codex token refresh returned no access token.")
        next_tokens = {
            **session["tokens"],
            "access_token": refreshed["access_token"],
            "refresh_token": refreshed.get("refresh_token") or session["tokens"].get("refresh_token"),
            "id_token": refreshed.get("id_token") or session["tokens"].get("id_token"),
        }
        next_session = {
            "auth_mode": session.get("auth_mode", "unknown"),
            "tokens": next_tokens,
            "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self.auth_path.write_text(json.dumps(next_session, indent=2) + "\n", encoding="utf-8")
        return next_session


def build_llm_client(config: LLMConfig) -> LLMClient:
    provider = config.provider.strip().lower()
    if provider in {"", "mock", "dry_run", "dry-run"}:
        return MockLLMClient()
    if provider in {"codex", "codex_oauth", "codex-oauth"}:
        return CodexOAuthClient(config)
    if provider in {"openai", "openai_compatible", "openai-compatible"}:
        return OpenAICompatibleClient(config)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")


def _default_codex_auth_path() -> Path:
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if not home:
        raise RuntimeError("Unable to resolve home directory for ~/.codex/auth.json")
    return Path(home) / ".codex" / "auth.json"


def _jwt_expiry(token: str) -> float | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
    except Exception:
        return None
    exp = data.get("exp")
    return float(exp) if isinstance(exp, (int, float)) else None


def _extract_response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts: list[str] = []
    for item in payload.get("output", []) or []:
        if item.get("type") == "message":
            for block in item.get("content", []) or []:
                if block.get("type") in {"output_text", "text"}:
                    parts.append(str(block.get("text", "")))
    if parts:
        return "".join(parts)
    return json.dumps(payload, ensure_ascii=False)


def _extract_sse_text(raw: str) -> str:
    parts: list[str] = []
    completed_payload: dict[str, Any] | None = None
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if not data:
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "response.output_text.delta" and event.get("delta"):
            parts.append(str(event["delta"]))
        if event.get("type") == "response.completed" and event.get("response"):
            completed_payload = event["response"]
    if parts:
        return "".join(parts)
    if completed_payload:
        return _extract_response_text(completed_payload)
    return raw

