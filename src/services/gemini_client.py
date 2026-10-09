"""
The agent's models, all free: writing, photographs, and checking photographs.

- Text and image checks go through g4f (GPT4Free), which reaches free model
  endpoints without a key. gemini-2.0-flash both writes the best Hindi of what
  answers and can read an image, so it leads both lists.
- Photos come from FLUX.1 on Hugging Face Spaces, called with gradio_client.
  Spaces run on a free daily GPU allowance tied to HF_TOKEN; the Inference API
  that this used to call no longer serves FLUX for free.

Free endpoints come and go, so every call walks a list and the error names
what was tried. The class keeps its old name so the agents need no changes.
"""
import io
import json
import logging
import os
import re
from typing import Optional

from g4f.client import Client as G4FClient

logger = logging.getLogger("gmap_scraper.gemini")


class GeminiError(Exception):
    """A call to a model failed; the message is safe to show a user."""


class ImageUnavailable(GeminiError):
    """
    No image model would take the request — usually the free daily GPU
    allowance is spent. Worth waiting for rather than failing the draft.
    `retry_after` is how many seconds Hugging Face said to wait, if it said.
    """

    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


def _retry_after(message: str) -> Optional[int]:
    """Seconds from Hugging Face's "Try again in 1:23:45", when it gives one."""
    m = re.search(r"[Tt]ry again in (\d+):(\d{2}):(\d{2})", message or "")
    if not m:
        return None
    h, mins, s = (int(x) for x in m.groups())
    return h * 3600 + mins * 60 + s


def _json_in(text: str) -> dict:
    """The outermost JSON object in an answer; models wrap it in prose or fences."""
    start, end = (text or "").find("{"), (text or "").rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"no JSON object in the answer: {(text or '')[:80]!r}")
    return json.loads(text[start:end + 1])


class GeminiClient:
    # Best Hindi first. These answered through g4f on 2026-10-09; the earlier
    # list (llama-3.1-*, mixtral, gpt-4o-mini first) no longer did.
    TEXT_MODELS = ["gemini-2.0-flash", "llama-3.3-70b", "gpt-4o-mini"]
    # The only free model found that reads images (and reads Devanagari).
    VISION_MODELS = ["gemini-2.0-flash"]
    # Dev draws lettering and faces better; Schnell is the quicker fallback
    # when Dev's queue or the day's GPU allowance runs out.
    IMAGE_SPACES = [
        ("black-forest-labs/FLUX.1-dev", {"guidance_scale": 3.5, "num_inference_steps": 28}),
        ("black-forest-labs/FLUX.1-schnell", {"num_inference_steps": 4}),
    ]

    def __init__(self):
        self.client = G4FClient()
        self.text_models = list(self.TEXT_MODELS)
        self.last_used_text_model = self.text_models[0]
        self.last_used_image_model = self.IMAGE_SPACES[0][0]

    def is_configured(self) -> bool:
        return True  # The free endpoints need no key; HF_TOKEN only raises the photo allowance.

    def text_model(self) -> str:
        return f"{self.last_used_text_model} (via g4f)"

    def generate_json(self, prompt: str, temperature: float = 1.0) -> dict:
        """Runs a prompt that must answer with one JSON object, trying each model."""
        for model in self.text_models:
            try:
                self.last_used_text_model = model
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt + "\n\nReply ONLY with valid JSON, no markdown or explanation."}],
                )
                return _json_in(response.choices[0].message.content)
            except Exception as e:
                logger.warning(f"gemini event=TEXT_MODEL_FAILED model={model} reason={str(e)[:160]}")

        # No made-up draft: a stand-in English one once reached the Studio as
        # if the agent had written it. The round fails and says why instead.
        raise GeminiError(f"No free text model answered (tried: {', '.join(self.text_models)}). Try again in a few minutes.")

    def generate_image(self, prompt: str, seed: Optional[int] = None) -> bytes:
        """One square image as JPEG bytes, from the first FLUX Space that answers."""
        from gradio_client import Client
        from PIL import Image

        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
        # The account's daily GPU allowance first, then the anonymous one,
        # which is counted separately (per address) once the account's is spent.
        callers = [token, None] if token else [None]
        tried, waits = [], []
        for (space, params), caller in ((s, c) for c in callers for s in self.IMAGE_SPACES):
            try:
                out = Client(space, token=caller, verbose=False).predict(
                    prompt=prompt, seed=seed or 0, randomize_seed=seed is None,
                    width=1024, height=1024, api_name="/infer", **params,
                )
                path = out[0] if isinstance(out, (list, tuple)) else out
                path = path.get("path") if isinstance(path, dict) else path
                buffer = io.BytesIO()
                # Spaces return WebP, which Meta does not take as a header.
                Image.open(path).convert("RGB").save(buffer, "JPEG", quality=92)
                self.last_used_image_model = space
                return buffer.getvalue()
            except Exception as e:
                tried.append(space.split("/")[-1] + ("" if caller else " (anonymous)"))
                wait = _retry_after(str(e))
                if wait:
                    waits.append(wait)
                logger.warning(f"gemini event=IMAGE_SPACE_FAILED space={space} "
                               f"anonymous={caller is None} reason={str(e)[:160]}")
        # The soonest any of them said it would take requests again.
        raise ImageUnavailable(
            f"No free image model answered (tried: {', '.join(tried)}). The Hugging Face "
            "Spaces may be busy, or the free daily GPU allowance used up.",
            retry_after=min(waits) if waits else None,
        )

    def inspect_image(self, image: bytes, mime_type: str, question: str) -> dict:
        """Asks a vision model a question about an image; answers with JSON."""
        ext = "png" if mime_type == "image/png" else "jpg"
        for model in self.VISION_MODELS:
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": question + "\n\nReply ONLY with valid JSON."}],
                    images=[[image, f"image.{ext}"]],
                )
                return _json_in(response.choices[0].message.content)
            except Exception as e:
                logger.warning(f"gemini event=VISION_MODEL_FAILED model={model} reason={str(e)[:160]}")
        raise GeminiError("No free model could look at the image")
