"""
Voice notes, turned into text with Whisper, so the bot can answer them.

Runs OpenAI's open Whisper model on this server through faster-whisper: no
account, no per-minute charge. The model ("small" by default, WHISPER_MODEL)
is downloaded once into WHISPER_CACHE_DIR, under data/ so a redeploy keeps
it, and loaded on the first voice note. On the user's own 4-second Hindi
note (2026-10-14) "small" wrote nonsense, "medium" came closest, and
"large-v3-turbo" was no better while taking twice the memory. None is
reliable on short Indian-language notes, which is why the bot leaves any
voice note it cannot act on for a person (onboarding_bot._fallback).

"small" stays the default because "medium" does not fit beside a scraping
batch's Chromium inside the backend's 4 GB memory limit: loading it during
a batch was killed for lack of memory, twice. WHISPER_MODEL=medium is for
when that limit (BACKEND_MEMORY_LIMIT) is raised.

The language is chosen among the bot's own (Indian languages and English),
not left to Whisper, which heard a short Hindi note as Polish; see
choose_language. Odia is not among Whisper's languages, so an Odia note is
transcribed in the nearest one it knows.
"""
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("gmap_scraper.transcribe")

MODEL = os.environ.get("WHISPER_MODEL", "small")
CACHE_DIR = os.environ.get("WHISPER_CACHE_DIR", os.path.join("data", "whisper"))
THREADS = int(os.environ.get("WHISPER_THREADS", "4"))

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


def _audio(path: str):
    from faster_whisper.audio import decode_audio
    return decode_audio(path, sampling_rate=16000)


def choose_language(model, audio, fallback_language: Optional[str] = None) -> tuple:
    """
    (language, probability) for a voice note, chosen among the bot's languages.

    Left to itself Whisper picks from a hundred languages, and on a short
    Hindi note it chose Polish. Its scores are kept for Indian languages and
    English only, Urdu counted as Hindi (Whisper hears spoken Hindi as Urdu
    and writes it in Urdu script), and the conversation's own language is
    preferred when the scores are close.
    """
    _lang, _prob, scores = model.detect_language(audio)
    kept: dict = {}
    for lang, p in scores:
        lang = "hi" if lang == "ur" else lang
        if lang in BOT_LANGUAGES:
            kept[lang] = kept.get(lang, 0.0) + p
    if fallback_language in BOT_LANGUAGES:
        kept[fallback_language] = kept.get(fallback_language, 0.0) * 1.5 + 0.05
    if not kept:
        return (fallback_language if fallback_language in BOT_LANGUAGES else "hi"), 0.0
    best = max(kept, key=kept.get)
    return best, round(kept[best], 2)


def transcribe(path: str, fallback_language: Optional[str] = None) -> dict:
    """
    {"text", "language", "probability"} for one audio file.

    The language is always one the bot speaks: chosen by choose_language,
    then the note is transcribed in it.
    """
    model = _load()
    audio = _audio(path)
    lang, prob = choose_language(model, audio, fallback_language)
    segments, _info = model.transcribe(audio, language=lang, beam_size=5, vad_filter=True)
    text = " ".join(s.text.strip() for s in segments).strip()
    return {"text": text, "language": lang, "probability": prob}
