"""
Voice notes, turned into text with Whisper, so the bot can answer them.

Runs OpenAI's open Whisper model on this server through faster-whisper: no
account, no per-minute charge. The model ("small" by default, WHISPER_MODEL)
is downloaded once into WHISPER_CACHE_DIR, under data/ so a redeploy keeps
it, and loaded on the first voice note. It takes about a gigabyte of memory
inside the backend's limit; "medium" understands Indian languages better but
takes about two, and is slower on CPU.

Whisper names the language it heard, and the bot answers in it. It often
calls spoken Hindi "Urdu" and writes it in Urdu script; such a note is
transcribed again as Hindi. Odia is not among Whisper's languages, so an
Odia voice note is transcribed as whatever it sounds closest to, and the
conversation's own language is used instead when Whisper is unsure.
"""
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("gmap_scraper.transcribe")

MODEL = os.environ.get("WHISPER_MODEL", "small")
CACHE_DIR = os.environ.get("WHISPER_CACHE_DIR", os.path.join("data", "whisper"))
THREADS = int(os.environ.get("WHISPER_THREADS", "4"))
# Below this, Whisper's guess at the language is not trusted.
SURE = 0.6

# Whisper's language codes the bot can answer in.
BOT_LANGUAGES = {"en", "hi", "mr", "pa", "gu", "bn", "ta", "te", "kn", "ml"}

_model = None
_lock = threading.Lock()


def _load():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel

            os.makedirs(CACHE_DIR, exist_ok=True)
            logger.info(f"transcribe event=LOADING model={MODEL}")
            _model = WhisperModel(MODEL, device="cpu", compute_type="int8",
                                  cpu_threads=THREADS, download_root=CACHE_DIR)
    return _model


def _run(path: str, language: Optional[str]):
    segments, info = _load().transcribe(path, language=language, beam_size=5, vad_filter=True)
    text = " ".join(s.text.strip() for s in segments).strip()
    return text, info.language, float(info.language_probability or 0)


def transcribe(path: str, fallback_language: Optional[str] = None) -> dict:
    """
    {"text", "language", "probability"} for one audio file.

    `language` is a code the bot speaks, or None when Whisper heard a
    language it does not. `fallback_language` is the conversation's own,
    used when Whisper is not sure what it heard.
    """
    text, lang, prob = _run(path, None)
    if lang == "ur":
        # Spoken Hindi, mostly; written out again in Devanagari.
        text, lang, prob = _run(path, "hi")[0], "hi", prob
    elif prob < SURE and fallback_language in BOT_LANGUAGES and fallback_language != lang:
        text, lang = _run(path, fallback_language)[0], fallback_language
    return {"text": text, "language": lang if lang in BOT_LANGUAGES else None, "probability": round(prob, 2)}
