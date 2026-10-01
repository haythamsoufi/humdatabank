"""NLLB translation sidecar for long-tail languages.

Fully self-hosted: on first boot it downloads ``facebook/nllb-200-1.3B`` from
Hugging Face, converts it to a quantized CTranslate2 model (cached under
``NLLB_CACHE_DIR`` so subsequent restarts skip the download/conversion), and
serves translations over HTTP using that local model. No external translation
API is called at request time.

When selected in the Backoffice it translates any mapped language, including
the core seven (en, fr, es, ar, ru, zh, hi). IFRC/Azure remains the default
engine unless the caller asks for NLLB.

The service reproduces the Backoffice placeholder contract: ``[variables]``,
``%(name)s``/``%s``, and Jinja ``{{ }}``/``{% %}`` tokens are protected before
translation and restored afterwards. This is defense-in-depth: the Backoffice
``AutoTranslator`` already protects placeholders with its own opaque tokens
before calling this service, but the sidecar honors the same contract when
called directly (e.g. by the Website or Mobile backends).

Model weights are Meta's NLLB-200 checkpoint, licensed CC-BY-NC 4.0. This
process does not fine-tune those weights.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Must be set before transformers/huggingface_hub resolve their cache paths
# (first import of either library "locks in" the cache location).
_CACHE_DIR = os.getenv("NLLB_CACHE_DIR", "/models")
os.environ.setdefault("HF_HOME", str(Path(_CACHE_DIR) / "hf-cache"))

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(level=os.getenv("NLLB_LOG_LEVEL", "INFO"))
logger = logging.getLogger("nllb-sidecar")

API_KEY = os.getenv("NLLB_SIDECAR_API_KEY", "")
CORE_LANGS = {"en", "fr", "es", "ar", "ru", "zh", "hi"}

MODEL_NAME = os.getenv("NLLB_MODEL_NAME", "facebook/nllb-200-1.3B")
# Hub snapshot for facebook/nllb-200-1.3B main. A revision change uses a new
# cache directory so a partial or older conversion is not reused.
MODEL_REVISION = os.getenv(
    "NLLB_MODEL_REVISION",
    "b0de46b488af0cf31749cd8da5ed3171e11b2309",
).strip()
QUANTIZATION = os.getenv("NLLB_QUANTIZATION", "int8")
CACHE_DIR = Path(_CACHE_DIR)
_REV_TAG = (MODEL_REVISION or "main")[:12]
MODEL_DIR = Path(
    os.getenv("NLLB_MODEL_DIR")
    or (CACHE_DIR / "ct2" / f"{MODEL_NAME.rsplit('/', 1)[-1]}-{QUANTIZATION}-{_REV_TAG}")
)
DEVICE = os.getenv("NLLB_DEVICE", "cpu")
INTER_THREADS = int(os.getenv("NLLB_INTER_THREADS", "1"))
INTRA_THREADS = int(os.getenv("NLLB_INTRA_THREADS", str(min(4, os.cpu_count() or 4))))
BEAM_SIZE = int(os.getenv("NLLB_BEAM_SIZE", "4"))
MAX_DECODING_LENGTH = int(os.getenv("NLLB_MAX_DECODING_LENGTH", "512"))
MAX_INPUT_CHARS = int(os.getenv("NLLB_MAX_INPUT_CHARS", "4000"))
MAX_SEGMENT_CHARS = int(os.getenv("NLLB_MAX_SEGMENT_CHARS", "600"))
MAX_BATCH_ITEMS = int(os.getenv("NLLB_MAX_BATCH_ITEMS", "256"))
CT2_BATCH_SIZE = max(1, int(os.getenv("NLLB_CT2_BATCH_SIZE", "16")))
# Smaller than any real int8 NLLB checkpoint; catches a killed conversion
# that left an empty or truncated model.bin.
_MIN_MODEL_BYTES = 8_000_000
# Test-only escape hatch: skip the (heavy) model download/conversion/load so
# the FastAPI routing/validation/placeholder logic can be unit-tested without
# torch/ctranslate2/transformers installed. Never set this in a real deployment.
DISABLE_MODEL_LOAD = os.getenv("NLLB_DISABLE_MODEL_LOAD", "").strip().lower() == "true"

app = FastAPI(title="IFRC NLLB sidecar", version="1.0.0")

if not API_KEY and not DISABLE_MODEL_LOAD:
    logger.warning(
        "NLLB_SIDECAR_API_KEY is unset. /api/translate is unauthenticated. "
        "Set a key before publishing this service beyond localhost."
    )


# ---------------------------------------------------------------------------
# ISO 639-1 -> FLORES-200 language code mapping
#
# Canonical table: iso1_to_flores200.json next to this file, vendored to
# Backoffice/config/nllb_iso1_to_flores200.json. A unit test fails if the
# copies diverge. Defaults (Chinese script, Serbian script, Kurdish variety,
# Norwegian, Fulah) and the Luba-Katanga omission are recorded in that file.
# ---------------------------------------------------------------------------
def _load_iso_map() -> Dict[str, str]:
    import json
    payload = json.loads(Path(__file__).with_name("iso1_to_flores200.json").read_text(encoding="utf-8"))
    languages = payload.get("languages") or payload
    return {str(key): str(value) for key, value in languages.items()}


ISO1_TO_FLORES200: Dict[str, str] = _load_iso_map()

_VALID_FLORES_CODES = set(ISO1_TO_FLORES200.values())

# Full tags checked before the region suffix is stripped. Plain "zh", "sr",
# and "ku" still use the defaults in the JSON file.
_TAG_TO_FLORES: Dict[str, str] = {
    "zh_hant": "zho_Hant",
    "zh_tw": "zho_Hant",
    "zh_hk": "zho_Hant",
    "zh_hans": "zho_Hans",
    "zh_cn": "zho_Hans",
    "sr_latn": "srp_Latn",
    "sr_cyrl": "srp_Cyrl",
    "ku_latn": "kmr_Latn",
    "kmr": "kmr_Latn",
    "ku_arab": "ckb_Arab",
    "ckb": "ckb_Arab",
}


def resolve_flores_code(code: Optional[str]) -> Optional[str]:
    """Resolve an ISO-639-1, script tag, or exact FLORES-200 code.

    Accepts exact FLORES-200 codes (``amh_Ethi``), ISO 639-1 codes (``am``),
    and script or region tags that must not fall through to the plain-code
    default (``zh_Hant``, ``zh-TW``, ``sr_Latn``, ``ckb``). Other region
    suffixes (``am_ET``, ``en-US``) are stripped before lookup.
    """
    if not code:
        return None
    raw = str(code).strip()
    if not raw:
        return None
    if raw in _VALID_FLORES_CODES:
        return raw
    normalized = raw.replace("-", "_")
    tagged = _TAG_TO_FLORES.get(normalized.lower())
    if tagged:
        return tagged
    base = normalized.lower().split("_", 1)[0]
    return ISO1_TO_FLORES200.get(base)


# ---------------------------------------------------------------------------
# Placeholder protection
# ---------------------------------------------------------------------------
_VAR = re.compile(
    r"\[[^\[\]]+\]"
    r"|%\([^)]{1,100}\)[#0\- +]{0,8}\d{0,10}(?:\.\d{1,10})?[sdfoxX]"
    r"|%(?!%)[#0\- +]{0,8}\d{0,10}(?:\.\d{1,10})?[sdfoxX]"
    r"|\{\{.*?\}\}"
    r"|\{%.*?%\}"
)
# Opaque, alphabetic-only (no digits: some scripts NLLB targets -- Devanagari,
# Bengali, Myanmar, ... -- localize Western numerals, which would break an
# exact-string restore).
_TOKEN_PREFIX = "NLLBXQZ"


def _make_token(counter: int) -> str:
    n = counter
    letters: List[str] = []
    while True:
        letters.append(chr(ord("A") + (n % 26)))
        n = (n // 26) - 1
        if n < 0:
            break
    return f"{_TOKEN_PREFIX}{''.join(reversed(letters))}"


def protect_placeholders(text: str) -> Tuple[str, Dict[str, str]]:
    """Replace placeholder-like substrings with opaque tokens before translation."""
    tokens: Dict[str, str] = {}
    counter = 0

    def _sub(m: "re.Match[str]") -> str:
        nonlocal counter
        tok = _make_token(counter)
        counter += 1
        tokens[tok] = m.group(0)
        return tok

    protected = _VAR.sub(_sub, text or "")
    return protected, tokens


def restore_placeholders(text: str, tokens: Dict[str, str]) -> str:
    """Restore protected placeholders. Appends any the model dropped (last resort)."""
    if not tokens:
        return text
    out = text
    for tok, original in tokens.items():
        out = out.replace(tok, original)
    missing = [original for tok, original in tokens.items() if original not in out]
    if missing:
        out = (out.rstrip() + " " + " ".join(missing)).strip()
    return out


# ---------------------------------------------------------------------------
# Model lifecycle: download + convert (once, cached) + load, in a background
# thread so the process starts serving /health immediately.
# ---------------------------------------------------------------------------
class _ModelState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        if DISABLE_MODEL_LOAD:
            self.status = "disabled"
            self.detail = "model load disabled (NLLB_DISABLE_MODEL_LOAD=true)"
        else:
            self.status = "loading"
            self.detail = "starting"
        self.error: Optional[str] = None
        self.translator = None
        self.tokenizer = None
        self.loaded_at: Optional[float] = None

    def set(self, *, status: str, detail: str = "", error: Optional[str] = None) -> None:
        with self.lock:
            self.status = status
            self.detail = detail
            self.error = error

    def snapshot(self) -> Dict[str, object]:
        with self.lock:
            return {
                "status": self.status,
                "detail": self.detail,
                "error": self.error,
                "loaded_at": self.loaded_at,
            }


_state = _ModelState()


def _model_is_converted() -> bool:
    weights = MODEL_DIR / "model.bin"
    config = MODEL_DIR / "config.json"
    if not weights.is_file() or not config.is_file():
        return False
    try:
        return weights.stat().st_size >= _MIN_MODEL_BYTES
    except OSError:
        return False


def _quarantine_model_dir() -> None:
    """Move a partial or unloadable conversion aside so the next start retries."""
    if not MODEL_DIR.exists():
        return
    dest = MODEL_DIR.with_name(f"{MODEL_DIR.name}.broken-{time.strftime('%Y%m%d%H%M%S')}")
    try:
        MODEL_DIR.rename(dest)
        logger.error("Moved unusable model dir to %s; next start will reconvert", dest)
    except OSError:
        logger.exception("Could not quarantine %s", MODEL_DIR)


def _convert_model() -> None:
    import shutil
    import subprocess

    exe = shutil.which("ct2-transformers-converter")
    if not exe:
        raise RuntimeError(
            "ct2-transformers-converter not found on PATH -- ctranslate2 is not installed correctly"
        )
    MODEL_DIR.parent.mkdir(parents=True, exist_ok=True)
    _state.set(
        status="loading",
        detail=(
            f"downloading + converting {MODEL_NAME}@{MODEL_REVISION[:12]} ({QUANTIZATION}) -- "
            "first boot can take 10-30+ minutes depending on bandwidth/CPU"
        ),
    )
    logger.info(
        "Converting %s@%s -> %s (quantization=%s)",
        MODEL_NAME,
        MODEL_REVISION,
        MODEL_DIR,
        QUANTIZATION,
    )
    cmd = [
        exe,
        "--model", MODEL_NAME,
        "--revision", MODEL_REVISION,
        "--output_dir", str(MODEL_DIR),
        "--quantization", QUANTIZATION,
        "--force",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-4000:]
        _quarantine_model_dir()
        raise RuntimeError(f"ct2-transformers-converter failed (exit {proc.returncode}): {tail}")
    if not _model_is_converted():
        _quarantine_model_dir()
        raise RuntimeError(f"Conversion finished but {MODEL_DIR} is incomplete")
    logger.info("Conversion complete: %s", MODEL_DIR)


def _load_tokenizer():
    import transformers

    kwargs = {"revision": MODEL_REVISION} if MODEL_REVISION else {}
    try:
        return transformers.AutoTokenizer.from_pretrained(
            MODEL_NAME, local_files_only=True, **kwargs
        )
    except Exception:
        logger.info("Tokenizer cache miss for %s@%s; downloading", MODEL_NAME, MODEL_REVISION)
        return transformers.AutoTokenizer.from_pretrained(MODEL_NAME, **kwargs)


def _load_model() -> None:
    if DISABLE_MODEL_LOAD:
        logger.warning("NLLB_DISABLE_MODEL_LOAD=true -- skipping model load; /api/translate will 503")
        return
    try:
        if not _model_is_converted():
            if MODEL_DIR.exists():
                logger.warning("Cached model at %s is incomplete; reconverting", MODEL_DIR)
                _quarantine_model_dir()
            _convert_model()
        else:
            logger.info("Using cached CTranslate2 model at %s", MODEL_DIR)

        _state.set(status="loading", detail="loading tokenizer + model into memory")
        import ctranslate2

        try:
            tokenizer = _load_tokenizer()
        except Exception as exc:
            logger.exception("NLLB tokenizer load failed")
            _state.set(status="error", detail="tokenizer load failed", error=str(exc))
            return

        try:
            translator = ctranslate2.Translator(
                str(MODEL_DIR),
                device=DEVICE,
                compute_type=QUANTIZATION,
                inter_threads=INTER_THREADS,
                intra_threads=INTRA_THREADS,
            )
        except Exception as exc:
            logger.exception("NLLB CTranslate2 model failed to load; quarantining %s", MODEL_DIR)
            _quarantine_model_dir()
            _state.set(status="error", detail="model load failed", error=str(exc))
            return

        with _state.lock:
            _state.tokenizer = tokenizer
            _state.translator = translator
            _state.status = "ready"
            _state.detail = f"{MODEL_NAME}@{MODEL_REVISION[:12]} ({QUANTIZATION}) ready on {DEVICE}"
            _state.error = None
            _state.loaded_at = time.time()
        logger.info("NLLB model ready: %s@%s", MODEL_NAME, MODEL_REVISION)
    except Exception as exc:  # pragma: no cover - startup failure path
        logger.exception("NLLB model load failed")
        _state.set(status="error", detail="model load failed", error=str(exc))


if not DISABLE_MODEL_LOAD:
    threading.Thread(target=_load_model, name="nllb-model-loader", daemon=True).start()


def _ensure_ready() -> None:
    snap = _state.snapshot()
    if snap["status"] != "ready":
        raise HTTPException(
            status_code=503,
            detail=f"NLLB model not ready ({snap['status']}): {snap['detail']}",
            headers={"Retry-After": "20"},
        )


# Serializes tokenizer.src_lang writes with translate_batch. CTranslate2 can
# serve one batch at a time on CPU; concurrent requests queue here.
_INFER_LOCK = threading.Lock()

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？؟؛])\s+|\n+")


def split_for_translation(text: str, max_chars: Optional[int] = None) -> List[str]:
    """Split long text into segments that fit the decoding cap.

    Placeholder tokens are alphabetic and contain no spaces, so a whitespace
    split does not cut them in half. Callers should protect placeholders first.
    """
    limit = max_chars if max_chars and max_chars > 0 else MAX_SEGMENT_CHARS
    raw = (text or "").strip()
    if not raw:
        return []
    if len(raw) <= limit:
        return [raw]

    pieces = [part.strip() for part in _SENTENCE_SPLIT.split(raw) if part and part.strip()]
    if not pieces:
        pieces = [raw]

    chunks: List[str] = []
    buf = ""

    def _flush_oversized(piece: str) -> None:
        nonlocal buf
        words = piece.split(" ")
        cur = ""
        for word in words:
            if not cur:
                cur = word
                continue
            if len(cur) + 1 + len(word) <= limit:
                cur = f"{cur} {word}"
            else:
                chunks.append(cur)
                cur = word
        while len(cur) > limit:
            chunks.append(cur[:limit])
            cur = cur[limit:]
        buf = cur

    for piece in pieces:
        if len(piece) > limit:
            if buf:
                chunks.append(buf)
                buf = ""
            _flush_oversized(piece)
            continue
        if buf and len(buf) + 1 + len(piece) > limit:
            chunks.append(buf)
            buf = piece
        elif buf:
            buf = f"{buf} {piece}"
        else:
            buf = piece
    if buf:
        chunks.append(buf)
    return chunks or [raw]


def _translate_batch_same_pair(
    texts: List[str],
    src_flores: str,
    tgt_flores: str,
) -> Tuple[List[str], List[bool]]:
    """Translate same-pair segments. Returns (strings, truncated flags).

    The lock covers ``src_lang`` and the CTranslate2 call so two requests
    cannot tokenize with each other's source language.
    """
    tokenizer = _state.tokenizer
    translator = _state.translator
    if tokenizer is None or translator is None:
        raise RuntimeError("NLLB model is not loaded")
    cap = max(8, MAX_DECODING_LENGTH)
    out_text: List[str] = []
    out_trunc: List[bool] = []
    with _INFER_LOCK:
        tokenizer.src_lang = src_flores
        step = CT2_BATCH_SIZE
        for start in range(0, len(texts), step):
            chunk = texts[start : start + step]
            sources = [
                tokenizer.convert_ids_to_tokens(tokenizer(segment).input_ids) for segment in chunk
            ]
            target_prefix = [[tgt_flores] for _ in chunk]
            results = translator.translate_batch(
                sources,
                target_prefix=target_prefix,
                beam_size=BEAM_SIZE,
                max_decoding_length=cap,
            )
            for result in results:
                toks = list(result.hypotheses[0])
                if toks and toks[0] == tgt_flores:
                    toks = toks[1:]
                truncated = len(toks) >= cap - 1
                ids = tokenizer.convert_tokens_to_ids(toks)
                out_text.append(tokenizer.decode(ids, skip_special_tokens=True).strip())
                out_trunc.append(truncated)
    return out_text, out_trunc


def _join_segments(source: str, parts: List[str]) -> str:
    joiner = "\n" if "\n" in (source or "") else " "
    return joiner.join(parts)


def _translate_protected_batch(
    jobs: List[Tuple[int, str, str, str]],
) -> Dict[int, Tuple[str, bool]]:
    """Translate protected strings, grouping every segment that shares a pair.

    ``jobs`` is ``(index, protected_text, src_flores, tgt_flores)``.
    """
    grouped: Dict[Tuple[str, str], List[Tuple[int, int, str]]] = {}
    counts: Dict[int, Tuple[str, int]] = {}
    for index, protected, src, tgt in jobs:
        segments = split_for_translation(protected)
        counts[index] = (protected, len(segments))
        for seg_index, segment in enumerate(segments):
            grouped.setdefault((src, tgt), []).append((index, seg_index, segment))

    rendered: Dict[Tuple[int, int], Tuple[str, bool]] = {}
    for (src, tgt), group in grouped.items():
        translated, flags = _translate_batch_same_pair([item[2] for item in group], src, tgt)
        for item, text, flag in zip(group, translated, flags):
            rendered[(item[0], item[1])] = (text, flag)

    assembled: Dict[int, Tuple[str, bool]] = {}
    for index, (protected, nsegs) in counts.items():
        parts: List[str] = []
        truncated = False
        for seg_index in range(nsegs):
            text, flag = rendered[(index, seg_index)]
            parts.append(text)
            truncated = truncated or flag
        assembled[index] = (_join_segments(protected, parts), truncated)
    return assembled


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class TranslateIn(BaseModel):
    Text: str = Field(..., min_length=1, max_length=MAX_INPUT_CHARS)
    From: str = "en"
    To: str


class TranslateOut(BaseModel):
    text: str
    engine: str = "nllb"
    # True when the source text was returned unchanged because it could not
    # be translated (unsupported code, empty input, or model not ready) --
    # only meaningful on the batch endpoint, which never raises per-item.
    deferred: bool = False
    # True when a segment hit max_decoding_length. Callers must not store
    # that string as a complete translation.
    truncated: bool = False


def _require_key(x_api_key: Optional[str]) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
def health():
    snap = _state.snapshot()
    return {
        "ok": snap["status"] == "ready",
        "status": snap["status"],
        "detail": snap["detail"],
        "error": snap["error"],
        "engine": "nllb",
        "model": MODEL_NAME,
        "quantization": QUANTIZATION,
        "device": DEVICE,
        "core_azure": sorted(CORE_LANGS),
    }


@app.get("/languages")
def languages(x_api_key: Optional[str] = Header(default=None)):
    _require_key(x_api_key)
    return {
        "core_azure": sorted(CORE_LANGS),
        "sidecar_supported": sorted(ISO1_TO_FLORES200.keys()),
        "model": MODEL_NAME,
        "revision": MODEL_REVISION,
        "license": "CC-BY-NC-4.0",
        "note": (
            "NLLB translates any mapped language, including the core seven. "
            "Plain zh is Simplified, sr is Cyrillic, ku is Kurmanji; "
            "pass zh_Hant, sr_Latn, or ckb to select the other written form. "
            "lu (Luba-Katanga) is not supported."
        ),
    }


def _translate_payload(body: TranslateIn) -> TranslateOut:
    text = (body.Text or "").strip()
    if not text:
        return TranslateOut(text=body.Text or "", deferred=True)

    src_flores = resolve_flores_code(body.From)
    tgt_flores = resolve_flores_code(body.To)
    if not src_flores or not tgt_flores:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language code(s): From={body.From!r} To={body.To!r}",
        )

    _ensure_ready()
    protected, tokens = protect_placeholders(text)
    try:
        assembled = _translate_protected_batch([(0, protected, src_flores, tgt_flores)])
        translated, truncated = assembled[0]
    except Exception as exc:
        logger.exception("NLLB inference failed")
        raise HTTPException(status_code=500, detail=f"Translation failed: {exc}") from exc

    return TranslateOut(
        text=restore_placeholders(translated, tokens),
        deferred=False,
        truncated=truncated,
    )


@app.post("/api/translate", response_model=TranslateOut)
def translate(body: TranslateIn, x_api_key: Optional[str] = Header(default=None)):
    _require_key(x_api_key)
    return _translate_payload(body)


@app.post("/api/translate/batch", response_model=List[TranslateOut])
def translate_batch(items: List[TranslateIn], x_api_key: Optional[str] = Header(default=None)):
    """Translate a batch.

    Segments that share a language pair are sent to CTranslate2 together.
    A bad item (unsupported code, model not ready, or inference error) does
    not fail the whole batch: it comes back with ``deferred=True``.
    """
    _require_key(x_api_key)
    if len(items) > MAX_BATCH_ITEMS:
        raise HTTPException(
            status_code=413,
            detail=f"Batch exceeds {MAX_BATCH_ITEMS} items",
        )

    outputs: List[Optional[TranslateOut]] = [None] * len(items)
    ready: List[Tuple[int, str, str, str, Dict[str, str]]] = []
    model_ready = _state.snapshot()["status"] == "ready"
    for index, item in enumerate(items):
        text = (item.Text or "").strip()
        if not text:
            outputs[index] = TranslateOut(text=item.Text or "", deferred=True)
            continue
        src_flores = resolve_flores_code(item.From)
        tgt_flores = resolve_flores_code(item.To)
        if not src_flores or not tgt_flores or not model_ready:
            outputs[index] = TranslateOut(text=item.Text, deferred=True)
            continue
        protected, tokens = protect_placeholders(text)
        ready.append((index, protected, src_flores, tgt_flores, tokens))

    if ready:
        try:
            assembled = _translate_protected_batch(
                [(index, protected, src, tgt) for index, protected, src, tgt, _tokens in ready]
            )
        except Exception:
            logger.exception("NLLB batch inference failed")
            for index, _protected, _src, _tgt, _tokens in ready:
                outputs[index] = TranslateOut(text=items[index].Text, deferred=True)
        else:
            for index, _protected, _src, _tgt, tokens in ready:
                translated, truncated = assembled[index]
                outputs[index] = TranslateOut(
                    text=restore_placeholders(translated, tokens),
                    deferred=False,
                    truncated=truncated,
                )
    return [item if item is not None else TranslateOut(text="", deferred=True) for item in outputs]
