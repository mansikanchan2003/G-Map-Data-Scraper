"""
Thin client for the Gemini API: copywriting, photo generation and photo checks.

Gemini is used for all three so one key covers the whole agent. It is called
over REST with `requests`, like the Meta client, rather than through an SDK.

Model names change faster than this code does, so none is hard-wired: the
first model from each preference list that the key can actually see is used,
and GEMINI_TEXT_MODEL / GEMINI_IMAGE_MODEL override the choice outright.
"""
import base64
import json
import logging
import os
from typing import List, Optional

import requests

logger = logging.getLogger("gmap_scraper.gemini")

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"

# Best first. Pro models write noticeably better Indic copy than Flash.
TEXT_MODEL_PREFERENCE = [
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]
# The released Pro image model ahead of its preview: it is the most
# photographic of these, which is the rule that matters most for the photo.
IMAGE_MODEL_PREFERENCE = [
    "gemini-3-pro-image",
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-image",
    "gemini-2.5-flash-image",
]


class GeminiError(Exception):
    """A call to Gemini failed; the message is safe to show a user."""


# How Gemini says a model can never serve this key — a free-tier key has a
# quota of zero on Pro and image models, and retired models stay listed. Such
# a model is skipped for the rest of the process rather than retried.
_UNUSABLE = ("limit: 0", "no longer available", "is not found", "not supported")
# Worth moving to the next model for this call, but not giving up on.
_TRANSIENT = ("high demand", "overloaded", "try again later")

# Models found unusable, shared across clients so each round does not
# rediscover them.
_dead_models: set = set()
# Busy models, set aside until this time. Without it every call in a round
# waited on the same overloaded model before falling back.
_busy_until: dict = {}
BUSY_COOLDOWN_SECONDS = 300


class GeminiClient:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self._available: Optional[List[str]] = None
        self._last_used: dict = {}

    def is_configured(self) -> bool:
        return bool(self.api_key)

    # -- plumbing -----------------------------------------------------------

    def _redact(self, text: str) -> str:
        if text and self.api_key:
            return text.replace(self.api_key, "***")
        return text

    def _post(self, model: str, payload: dict, timeout: int) -> dict:
        if not self.api_key:
            raise GeminiError("GEMINI_API_KEY is not configured")
        try:
            r = requests.post(
                f"{API_ROOT}/models/{model}:generateContent",
                headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=timeout,
            )
        except requests.exceptions.Timeout:
            raise GeminiError(f"Gemini ({model}) timed out")
        except requests.exceptions.RequestException as e:
            raise GeminiError(f"Could not reach Gemini: {self._redact(str(e))}")

        try:
            data = r.json()
        except ValueError:
            raise GeminiError(f"Gemini ({model}) answered HTTP {r.status_code} with no JSON")
        if r.status_code != 200:
            msg = (data.get("error") or {}).get("message") or f"HTTP {r.status_code}"
            raise GeminiError(f"Gemini ({model}) refused the request: {self._redact(msg)}")
        return data

    def available_models(self) -> List[str]:
        """Model ids this key can call, without the 'models/' prefix."""
        if self._available is not None:
            return self._available
        if not self.api_key:
            raise GeminiError("GEMINI_API_KEY is not configured")
        try:
            r = requests.get(
                f"{API_ROOT}/models",
                headers={"x-goog-api-key": self.api_key},
                params={"pageSize": 1000},
                timeout=20,
            )
            data = r.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            raise GeminiError(f"Could not list Gemini models: {self._redact(str(e))}")
        if r.status_code != 200:
            msg = (data.get("error") or {}).get("message") or f"HTTP {r.status_code}"
            raise GeminiError(f"Gemini refused the model listing: {self._redact(msg)}")
        self._available = [m["name"].split("/", 1)[-1] for m in data.get("models", [])]
        return self._available

    def _candidates(self, env_var: str, preference: List[str]) -> List[str]:
        override = os.environ.get(env_var)
        if override:
            return [override]
        import time

        available = set(self.available_models())
        usable = [m for m in preference if m in available and m not in _dead_models]
        now = time.time()
        rested = [m for m in usable if _busy_until.get(m, 0) <= now]
        # Busy ones stay at the back rather than vanishing, in case nothing else answers.
        return rested + [m for m in usable if m not in rested]

    def _call(self, kind: str, payload: dict, timeout: int) -> dict:
        """
        Calls the best model of a kind that will actually serve this key.

        A model the key cannot use is skipped and remembered; a busy one is
        skipped for this call only. The error names every model tried, so a
        failure says what to fix — usually billing, for photos.
        """
        env_var, preference = (
            ("GEMINI_TEXT_MODEL", TEXT_MODEL_PREFERENCE) if kind == "text"
            else ("GEMINI_IMAGE_MODEL", IMAGE_MODEL_PREFERENCE)
        )
        tried = []
        for model in self._candidates(env_var, preference):
            try:
                data = self._post(model, payload, timeout)
                self._last_used[kind] = model
                return data
            except GeminiError as e:
                msg = str(e)
                if any(s in msg for s in _UNUSABLE):
                    _dead_models.add(model)
                elif any(s in msg.lower() for s in _TRANSIENT):
                    import time
                    _busy_until[model] = time.time() + BUSY_COOLDOWN_SECONDS
                else:
                    raise
                tried.append(model)
                logger.warning(f"gemini event=MODEL_SKIPPED kind={kind} model={model} reason={msg[:160]}")
        hint = (" Photo generation needs billing enabled on the Google project behind "
                "GEMINI_API_KEY; the free tier allows no image models." if kind == "image" else "")
        # Models found unusable on an earlier call count as tried too.
        tried += [m for m in preference if m in _dead_models and m not in tried]
        raise GeminiError(
            f"No {kind} model is usable with this API key (tried: {', '.join(tried) or 'none listed'}).{hint}"
        )

    def text_model(self) -> str:
        """The text model last used, or the one that would be tried first."""
        return self._last_used.get("text") or (self._candidates("GEMINI_TEXT_MODEL", TEXT_MODEL_PREFERENCE) or ["none"])[0]

    def image_model(self) -> str:
        return self._last_used.get("image") or (self._candidates("GEMINI_IMAGE_MODEL", IMAGE_MODEL_PREFERENCE) or ["none"])[0]

    @staticmethod
    def _text_of(data: dict) -> str:
        for cand in data.get("candidates", []):
            parts = (cand.get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts if "text" in p)
            if text:
                return text
        reason = (data.get("promptFeedback") or {}).get("blockReason")
        raise GeminiError(f"Gemini returned no text{f' (blocked: {reason})' if reason else ''}")

    # -- the three things the agent asks for --------------------------------

    def generate_json(self, prompt: str, temperature: float = 1.0) -> dict:
        """Runs a prompt that must answer with one JSON object."""
        data = self._call("text", {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": temperature},
        }, timeout=180)
        text = self._text_of(data)
        try:
            return json.loads(text)
        except ValueError:
            raise GeminiError("Gemini's answer was not valid JSON")

    def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> bytes:
        """Generates one image and returns its bytes (PNG or JPEG)."""
        data = self._call("image", {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {"aspectRatio": aspect_ratio},
            },
        }, timeout=240)
        for cand in data.get("candidates", []):
            for part in (cand.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"])
        reason = (data.get("promptFeedback") or {}).get("blockReason")
        raise GeminiError(f"Gemini returned no image{f' (blocked: {reason})' if reason else ''}")

    def inspect_image(self, image: bytes, mime_type: str, question: str) -> dict:
        """Asks the text model a question about an image; answers with JSON."""
        data = self._call("text", {
            "contents": [{"role": "user", "parts": [
                {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(image).decode()}},
                {"text": question},
            ]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.0},
        }, timeout=120)
        try:
            return json.loads(self._text_of(data))
        except ValueError:
            raise GeminiError("Gemini's image check was not valid JSON")
