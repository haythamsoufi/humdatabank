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
QUANTIZATION = os.getenv("NLLB_QUANTIZATION", "int8")
CACHE_DIR = Path(_CACHE_DIR)
MODEL_DIR = Path(
    os.getenv("NLLB_MODEL_DIR")
    or (CACHE_DIR / "ct2" / f"{MODEL_NAME.rsplit('/', 1)[-1]}-{QUANTIZATION}")
)
DEVICE = os.getenv("NLLB_DEVICE", "cpu")
INTER_THREADS = int(os.getenv("NLLB_INTER_THREADS", "1"))
INTRA_THREADS = int(os.getenv("NLLB_INTRA_THREADS", str(min(4, os.cpu_count() or 4))))
BEAM_SIZE = int(os.getenv("NLLB_BEAM_SIZE", "4"))
MAX_DECODING_LENGTH = int(os.getenv("NLLB_MAX_DECODING_LENGTH", "256"))
MAX_INPUT_CHARS = int(os.getenv("NLLB_MAX_INPUT_CHARS", "4000"))
# Test-only escape hatch: skip the (heavy) model download/conversion/load so
# the FastAPI routing/validation/placeholder logic can be unit-tested without
# torch/ctranslate2/transformers installed. Never set this in a real deployment.
DISABLE_MODEL_LOAD = os.getenv("NLLB_DISABLE_MODEL_LOAD", "").strip().lower() == "true"

app = FastAPI(title="IFRC NLLB sidecar", version="1.0.0")


# ---------------------------------------------------------------------------
# ISO 639-1 -> FLORES-200 language code mapping
#
# NLLB-200 identifies languages with a FLORES-200 code: ISO-639-3 + script
# (e.g. "amh_Ethi"). Our app config (Backoffice ``Config.ALL_LANGUAGES_DISPLAY_NAMES``)
# uses plain ISO 639-1 codes everywhere, so this table is the only place that
# needs to know about FLORES-200 -- callers (the Backoffice AutoTranslator, or
# anyone else) just send ordinary 2-letter codes like "am", "sw", "ne".
#
# Where an ISO 639-1 code covers a macrolanguage with several FLORES-200
# variants (script or dialect), we pick the variant with the widest reach /
# the "standard" written form: Arabic -> Modern Standard Arabic (arb_Arab),
# Chinese -> Simplified (zho_Hans), Persian -> Western/Iranian (pes_Arab),
# Malay -> Standard Malay (zsm_Latn), Azerbaijani -> North (azj_Latn),
# Uzbek -> Northern (uzn_Latn), Latvian -> Standard (lvs_Latn),
# Mongolian -> Halh (khk_Cyrl), Albanian -> Tosk (als_Latn),
# Norwegian -> Bokmål (nob_Latn), Kurdish -> Northern/Kurmanji (kmr_Latn),
# Oromo -> West Central (gaz_Latn), Pashto -> Southern (pbt_Arab),
# Quechua -> Ayacucho (quy_Latn), Malagasy -> Plateau (plt_Latn).
# Source: https://github.com/facebookresearch/flores/blob/main/flores200/README.md
# ---------------------------------------------------------------------------
ISO1_TO_FLORES200: Dict[str, str] = {
    # Core seven (also valid "To" targets when NLLB is selected).
    "en": "eng_Latn",
    "fr": "fra_Latn",
    "es": "spa_Latn",
    "ar": "arb_Arab",
    "ru": "rus_Cyrl",
    "zh": "zho_Hans",
    "hi": "hin_Deva",
    # Africa
    "af": "afr_Latn",
    "ak": "aka_Latn",
    "am": "amh_Ethi",
    "ee": "ewe_Latn",
    "ff": "fuv_Latn",
    "ha": "hau_Latn",
    "ig": "ibo_Latn",
    "ki": "kik_Latn",
    "kg": "kon_Latn",
    "ln": "lin_Latn",
    "lg": "lug_Latn",
    "mg": "plt_Latn",
    "ny": "nya_Latn",
    "om": "gaz_Latn",
    "rn": "run_Latn",
    "rw": "kin_Latn",
    "sg": "sag_Latn",
    "sn": "sna_Latn",
    "so": "som_Latn",
    "st": "sot_Latn",
    "ss": "ssw_Latn",
    "sw": "swh_Latn",
    "ti": "tir_Ethi",
    "tn": "tsn_Latn",
    "ts": "tso_Latn",
    "tw": "twi_Latn",
    "wo": "wol_Latn",
    "xh": "xho_Latn",
    "yo": "yor_Latn",
    "zu": "zul_Latn",
    # Middle East / Central Asia
    "fa": "pes_Arab",
    "he": "heb_Hebr",
    "ku": "kmr_Latn",
    "ps": "pbt_Arab",
    "tg": "tgk_Cyrl",
    "tk": "tuk_Latn",
    "tr": "tur_Latn",
    "ug": "uig_Arab",
    "ur": "urd_Arab",
    "uz": "uzn_Latn",
    "az": "azj_Latn",
    "hy": "hye_Armn",
    "ka": "kat_Geor",
    "kk": "kaz_Cyrl",
    "ky": "kir_Cyrl",
    "mn": "khk_Cyrl",
    "kr": "knc_Latn",
    "ks": "kas_Arab",
    # South Asia
    "as": "asm_Beng",
    "bn": "ben_Beng",
    "gu": "guj_Gujr",
    "kn": "kan_Knda",
    "ml": "mal_Mlym",
    "mr": "mar_Deva",
    "ne": "npi_Deva",
    "or": "ory_Orya",
    "pa": "pan_Guru",
    "sa": "san_Deva",
    "sd": "snd_Arab",
    "si": "sin_Sinh",
    "ta": "tam_Taml",
    "te": "tel_Telu",
    # Southeast Asia / East Asia
    "id": "ind_Latn",
    "jv": "jav_Latn",
    "km": "khm_Khmr",
    "lo": "lao_Laoo",
    "ms": "zsm_Latn",
    "my": "mya_Mymr",
    "su": "sun_Latn",
    "th": "tha_Thai",
    "tl": "tgl_Latn",
    "vi": "vie_Latn",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "mi": "mri_Latn",
    "sm": "smo_Latn",
    "fj": "fij_Latn",
    # Europe
    "sq": "als_Latn",
    "be": "bel_Cyrl",
    "bs": "bos_Latn",
    "bg": "bul_Cyrl",
    "ca": "cat_Latn",
    "hr": "hrv_Latn",
    "cs": "ces_Latn",
    "da": "dan_Latn",
    "nl": "nld_Latn",
    "eo": "epo_Latn",
    "et": "est_Latn",
    "eu": "eus_Latn",
    "fi": "fin_Latn",
    "gl": "glg_Latn",
    "de": "deu_Latn",
    "el": "ell_Grek",
    "ht": "hat_Latn",
    "hu": "hun_Latn",
    "is": "isl_Latn",
    "ga": "gle_Latn",
    "it": "ita_Latn",
    "lv": "lvs_Latn",
    "lt": "lit_Latn",
    "lb": "ltz_Latn",
    "mk": "mkd_Cyrl",
    "mt": "mlt_Latn",
    "nb": "nob_Latn",
    "nn": "nno_Latn",
    "no": "nob_Latn",
    "oc": "oci_Latn",
    "pl": "pol_Latn",
    "pt": "por_Latn",
    "ro": "ron_Latn",
    "gd": "gla_Latn",
    "sr": "srp_Cyrl",
    "sk": "slk_Latn",
    "sl": "slv_Latn",
    "sc": "srd_Latn",
    "sv": "swe_Latn",
    "cy": "cym_Latn",
    "uk": "ukr_Cyrl",
    "yi": "ydd_Hebr",
    "fo": "fao_Latn",
    "ba": "bak_Cyrl",
    "bm": "bam_Latn",
    "bo": "bod_Tibt",
    "dz": "dzo_Tibt",
    "gn": "grn_Latn",
    "li": "lim_Latn",
    "lu": "lua_Latn",
    "qu": "quy_Latn",
    "ay": "ayr_Latn",
    "tt": "tat_Cyrl",
}

_VALID_FLORES_CODES = set(ISO1_TO_FLORES200.values())


def resolve_flores_code(code: Optional[str]) -> Optional[str]:
    """Resolve an ISO-639-1 (or exact FLORES-200) code to a FLORES-200 code.

    Accepts:
    - Exact FLORES-200 codes (e.g. "amh_Ethi") for advanced/direct callers.
    - ISO 639-1 codes (e.g. "am"), with optional region/script suffix
      ("am_ET", "am-ET") which is stripped before lookup.
    """
    if not code:
        return None
    raw = str(code).strip()
    if not raw:
        return None
    if raw in _VALID_FLORES_CODES:
        return raw
    base = raw.replace("-", "_").lower().split("_", 1)[0]
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
    return (MODEL_DIR / "model.bin").exists()


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
            f"downloading + converting {MODEL_NAME} ({QUANTIZATION}) -- "
            "first boot can take 10-30+ minutes depending on bandwidth/CPU"
        ),
    )
    logger.info("Converting %s -> %s (quantization=%s)", MODEL_NAME, MODEL_DIR, QUANTIZATION)
    proc = subprocess.run(
        [
            exe,
            "--model", MODEL_NAME,
            "--output_dir", str(MODEL_DIR),
            "--quantization", QUANTIZATION,
            "--force",
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-4000:]
        raise RuntimeError(f"ct2-transformers-converter failed (exit {proc.returncode}): {tail}")
    logger.info("Conversion complete: %s", MODEL_DIR)


def _load_model() -> None:
    if DISABLE_MODEL_LOAD:
        logger.warning("NLLB_DISABLE_MODEL_LOAD=true -- skipping model load; /api/translate will 503")
        return
    try:
        if not _model_is_converted():
            _convert_model()
        else:
            logger.info("Using cached CTranslate2 model at %s", MODEL_DIR)

        _state.set(status="loading", detail="loading tokenizer + model into memory")
        import ctranslate2
        import transformers

        tokenizer = transformers.AutoTokenizer.from_pretrained(MODEL_NAME)
        translator = ctranslate2.Translator(
            str(MODEL_DIR),
            device=DEVICE,
            compute_type=QUANTIZATION,
            inter_threads=INTER_THREADS,
            intra_threads=INTRA_THREADS,
        )
        with _state.lock:
            _state.tokenizer = tokenizer
            _state.translator = translator
            _state.status = "ready"
            _state.detail = f"{MODEL_NAME} ({QUANTIZATION}) ready on {DEVICE}"
            _state.error = None
            _state.loaded_at = time.time()
        logger.info("NLLB model ready: %s", MODEL_NAME)
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


def _translate_batch_same_pair(texts: List[str], src_flores: str, tgt_flores: str) -> List[str]:
    tokenizer = _state.tokenizer
    translator = _state.translator
    tokenizer.src_lang = src_flores
    sources = [tokenizer.convert_ids_to_tokens(tokenizer(t).input_ids) for t in texts]
    target_prefix = [[tgt_flores] for _ in texts]
    results = translator.translate_batch(
        sources,
        target_prefix=target_prefix,
        beam_size=BEAM_SIZE,
        max_decoding_length=MAX_DECODING_LENGTH,
    )
    out: List[str] = []
    for r in results:
        toks = r.hypotheses[0]
        if toks and toks[0] == tgt_flores:
            toks = toks[1:]
        ids = tokenizer.convert_tokens_to_ids(toks)
        out.append(tokenizer.decode(ids, skip_special_tokens=True).strip())
    return out


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
def languages():
    return {
        "core_azure": sorted(CORE_LANGS),
        "sidecar_supported": sorted(ISO1_TO_FLORES200.keys()),
        "model": MODEL_NAME,
        "note": "NLLB translates any mapped language, including the core seven",
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
        translated = _translate_batch_same_pair([protected], src_flores, tgt_flores)[0]
    except Exception as exc:
        logger.exception("NLLB inference failed")
        raise HTTPException(status_code=500, detail=f"Translation failed: {exc}") from exc

    return TranslateOut(text=restore_placeholders(translated, tokens), deferred=False)


@app.post("/api/translate", response_model=TranslateOut)
def translate(body: TranslateIn, x_api_key: Optional[str] = Header(default=None)):
    _require_key(x_api_key)
    return _translate_payload(body)


@app.post("/api/translate/batch", response_model=List[TranslateOut])
def translate_batch(items: List[TranslateIn], x_api_key: Optional[str] = Header(default=None)):
    """Translate a batch. Unlike /api/translate, a single bad item
    (unsupported code or model not ready) does not fail the whole batch --
    it comes back with ``deferred=True`` and the source text unchanged.
    """
    _require_key(x_api_key)
    out: List[TranslateOut] = []
    for item in items:
        try:
            out.append(_translate_payload(item))
        except HTTPException as exc:
            logger.info("batch item skipped (%s): %s", exc.status_code, exc.detail)
            out.append(TranslateOut(text=item.Text, deferred=True))
    return out
