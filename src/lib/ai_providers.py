# ai_providers.py
#
# SPDX-License-Identifier: GPL-3.0-or-later

import threading
import logging

import requests

logger = logging.getLogger(__name__)

PROVIDER_DEFAULTS = {
    "openai": "gpt-5-mini",
    "anthropic": "claude-haiku-4-5",
    "gemini": "gemini-2.5-flash",
    "ollama": "llama3.2",
}


class ProviderAuthError(Exception):
    pass


class ProviderModelError(Exception):
    def __init__(self, model_id: str):
        self.model_id = model_id
        super().__init__(f"Model not found: {model_id}")


def _check_errors(response, provider: str, model_id: str) -> None:
    if response.status_code in (401, 403):
        raise ProviderAuthError(f"Authentication failed for {provider}")
    if response.status_code == 404:
        raise ProviderModelError(model_id)
    response.raise_for_status()


def call_openai(
    messages: list,
    api_key: str,
    model: str,
    cancel_event: threading.Event,
    system: str = "",
) -> str:
    if cancel_event.is_set():
        raise InterruptedError("Cancelled")

    resolved_model = model or PROVIDER_DEFAULTS["openai"]
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    response = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={"model": resolved_model, "messages": all_messages},
        timeout=30,
    )
    _check_errors(response, "openai", resolved_model)
    return response.json()["choices"][0]["message"]["content"]


def call_anthropic(
    messages: list,
    api_key: str,
    model: str,
    cancel_event: threading.Event,
    system: str = "",
) -> str:
    if cancel_event.is_set():
        raise InterruptedError("Cancelled")

    resolved_model = model or PROVIDER_DEFAULTS["anthropic"]
    payload: dict = {
        "model": resolved_model,
        "max_tokens": 1024,
        "messages": messages,
    }
    if system:
        payload["system"] = system

    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    _check_errors(response, "anthropic", resolved_model)
    return response.json()["content"][0]["text"]


def call_gemini(
    messages: list,
    api_key: str,
    model: str,
    cancel_event: threading.Event,
    system: str = "",
) -> str:
    if cancel_event.is_set():
        raise InterruptedError("Cancelled")

    resolved_model = model or PROVIDER_DEFAULTS["gemini"]
    contents = [
        {
            "role": "user" if m["role"] == "user" else "model",
            "parts": [{"text": m["content"]}],
        }
        for m in messages
    ]
    payload: dict = {"contents": contents}
    if system:
        payload["system_instruction"] = {"parts": [{"text": system}]}

    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{resolved_model}:generateContent",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        json=payload,
        timeout=30,
    )
    _check_errors(response, "gemini", resolved_model)
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]


def call_ollama(
    messages: list,
    model: str,
    base_url: str,
    cancel_event: threading.Event,
    system: str = "",
) -> str:
    if cancel_event.is_set():
        raise InterruptedError("Cancelled")

    resolved_model = model or PROVIDER_DEFAULTS["ollama"]
    all_messages = []
    if system:
        all_messages.append({"role": "system", "content": system})
    all_messages.extend(messages)

    response = requests.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={"model": resolved_model, "messages": all_messages, "stream": False},
        timeout=30,
    )
    _check_errors(response, "ollama", resolved_model)
    return response.json()["message"]["content"]
