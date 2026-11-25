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

A Hindi note is then written out by a "small" Whisper trained further on
Hindi speech (HINDI_MODEL, Collabora's conversion of IIT Madras's model,
free like the rest). On that same note it wrote "मुझे क्वेश्चन पूछना होगा",
what was said, where every general model wrote nonsense. It is about as
large as "small", so both fit beside a scraping batch.
"""
import logging
import os
import threading
from typing import Optional

logger = logging.getLogger("gmap_scraper.transcribe")

MODEL = os.environ.get("WHISPER_MODEL", "small")
CACHE_DIR = os.environ.get("WHISPER_CACHE_DIR", os.path.join("data", "whisper"))
HINDI_MODEL = os.environ.get("WHISPER_HINDI_MODEL", "collabora/faster-whisper-small-hindi")
THREADS = int(os.environ.get("WHISPER_THREADS", "4"))

# Whisper's language codes the bot can answer in.
BOT_LANGUAGES = {"en", "hi", "mr", "pa", "gu", "bn", "ta", "te", "kn", "ml"}

_models: dict = {}
_lock = threading.Lock()
# Both models together hold about a gigabyte. Voice notes come a few a day, so a model
# unused this long is let go and loaded again for the next note, in a few seconds
# (25 Nov 2026: kept for good, they held the website at half its memory all day).
IDLE_MINUTES = float(os.environ.get("WHISPER_IDLE_MINUTES", "15"))
_last_used: dict = {}
_reaper: Optional[threading.Thread] = None


def _load(name: str = None):
    name = name or MODEL
    with _lock:
        if name not in _models:
            from faster_whisper import WhisperModel

            os.makedirs(CACHE_DIR, exist_ok=True)
            logger.info(f"transcribe event=LOADING model={name}")
            _models[name] = WhisperModel(name, device="cpu", compute_type="int8",
                                         cpu_threads=THREADS, download_root=CACHE_DIR)
        _last_used[name] = _now()
        _start_reaper()
    return _models[name]


def _now() -> float:
    import time
    return time.monotonic()


def unload_idle(idle_seconds: Optional[float] = None) -> list:
    """Lets go of models unused for idle_seconds (IDLE_MINUTES by default); returns their names."""
    import gc
    limit = IDLE_MINUTES * 60 if idle_seconds is None else idle_seconds
    gone = []
    with _lock:
        for name in list(_models):
            if _now() - _last_used.get(name, 0) >= limit:
                del _models[name]
                _last_used.pop(name, None)
                gone.append(name)
    if gone:
        gc.collect()
        logger.info(f"transcribe event=UNLOADED models={gone}")
    return gone


def _start_reaper() -> None:
    global _reaper
    if IDLE_MINUTES <= 0 or (_reaper and _reaper.is_alive()):
        return

    def loop():
        import time
        while True:
            time.sleep(60)
            try:
                unload_idle()
            except Exception:
                logger.warning("transcribe event=UNLOAD_FAILED", exc_info=True)

    _reaper = threading.Thread(target=loop, name="whisper-unload", daemon=True)
    _reaper.start()


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
    then the note is transcribed in it, by the Hindi model if it is Hindi.
    """
    model = _load()
    audio = _audio(path)
    lang, prob = choose_language(model, audio, fallback_language)
    if lang == "hi" and HINDI_MODEL:
        try:
            model = _load(HINDI_MODEL)
        except Exception:
            logger.exception(f"transcribe event=HINDI_MODEL_FAILED model={HINDI_MODEL}")
    segments, _info = model.transcribe(audio, language=lang, beam_size=5, vad_filter=True)
    text = " ".join(s.text.strip() for s in segments).strip()
    return {"text": text, "language": lang, "probability": prob}
