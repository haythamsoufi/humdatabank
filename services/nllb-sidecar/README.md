# NLLB sidecar

Self-hosted machine translation (CTranslate2 + NLLB-200). IFRC/Azure remains the **default**
Backoffice engine. When NLLB is selected in the UI, it translates every mapped language,
including the core seven (`en, fr, es, ar, ru, zh, hi`).

The weights are [CC-BY-NC 4.0](https://huggingface.co/facebook/nllb-200-1.3B) (non-commercial use, attribution required). This service does not fine-tune them. Admins improve wording through the glossary, not by uploading documents into the model. See the [admin guide](../../Backoffice/docs/user-guides/admin/nllb-translation.md).

## How it works

- Model: [`facebook/nllb-200-1.3B`](https://huggingface.co/facebook/nllb-200-1.3B) at revision
  `b0de46b488af0cf31749cd8da5ed3171e11b2309` (`NLLB_MODEL_REVISION`), quantized to `int8` and served
  with [CTranslate2](https://github.com/OpenNMT/CTranslate2). The cache directory includes the revision,
  so a pin change reconverts instead of reusing an older `model.bin`.
- **No external API calls at request time** -- translation runs entirely inside this container, on CPU.
- On first boot the container downloads the model from Hugging Face and converts it to a CTranslate2
  model (`ct2-transformers-converter --quantization int8`). This takes **10-30+ minutes** and needs
  ~6GB of disk, depending on bandwidth/CPU. The converted model is cached on the `nllb_models` volume
  (`/models` in the container), so subsequent restarts skip straight to loading (a few seconds).
- `/health` reports the real state (`loading` / `ready` / `error`) -- `ok: true` only once the model
  is actually loaded and serving. `/api/translate` returns `503` (with `Retry-After`) while loading,
  rather than silently echoing the source text.
- Long inputs are split into segments. If a segment still hits the decoding cap, the response sets
  `truncated: true` and the Backoffice client discards it.
- Inference is serialized. Segments that share a language pair in one batch are translated together.
- A partial or unloadable conversion is moved to `*.broken-<timestamp>` so the next start reconverts.
  A tokenizer download failure does not throw away a good CTranslate2 directory.

## Running it

```bash
docker compose --profile nllb up -d --build
docker compose logs -f nllb        # watch download/conversion progress
curl http://127.0.0.1:9100/health  # {"ok": false, "status": "loading", ...} until ready
```

Compose publishes the port on `127.0.0.1` only. Set `NLLB_SIDECAR_API_KEY` (and the same value on
the Backoffice) before exposing the service any wider. `/health` stays open for the container
healthcheck. `/languages` and `/api/translate*` require the key when it is set.

Once `ok: true`:

```bash
curl -X POST http://localhost:9100/api/translate \
  -H "Content-Type: application/json" \
  -d '{"Text": "Please evacuate the area immediately.", "From": "en", "To": "am"}'
# {"text": "...", "engine": "nllb", "deferred": false}
```

Core languages are valid targets too:

```bash
curl -X POST http://localhost:9100/api/translate \
  -H "Content-Type: application/json" -d '{"Text": "hello", "From": "en", "To": "fr"}'
# {"text": "...", "engine": "nllb", "deferred": false}
```

## Using it from the Backoffice

The sidecar is opt-in and disabled unless explicitly pointed at:

```bash
# Backoffice service env (docker-compose.yml has this commented out by default)
NLLB_SIDECAR_URL=http://nllb:9100
NLLB_SIDECAR_API_KEY=   # optional, must match the sidecar's NLLB_SIDECAR_API_KEY
```

Once set, `NLLBTranslationService` registers as the `nllb` engine in
`app/services/translation/auto_translator.py` and shows up in the auto-translate service picker
(`/admin/api/translation_services`) and the quality dashboard. It is never the *default* engine.
Selecting it in the UI uses NLLB for every target language.
The Backoffice already protects `[variables]`, `%(name)s`, and Jinja `{{ }}` tokens before calling
any engine (`AutoTranslator._protect_variables`); this sidecar's own `/api/translate` reproduces the
same contract independently for direct callers (Website, Mobile, curl).

## Language coverage

`GET /languages` lists the ISO 639-1 codes in `iso1_to_flores200.json` (vendored to
`Backoffice/config/nllb_iso1_to_flores200.json`; a unit test fails if the copies diverge).
Codes not in that table return `400`.

Plain codes use one written form. Pass a script tag when you need the other one:

| Tag | FLORES code |
|---|---|
| `zh` (also `zh_Hans`, `zh_CN`) | `zho_Hans` |
| `zh_Hant`, `zh_TW`, `zh_HK` | `zho_Hant` |
| `sr` | `srp_Cyrl` |
| `sr_Latn` | `srp_Latn` |
| `ku` (also `kmr`, `ku_Latn`) | `kmr_Latn` |
| `ckb`, `ku_Arab` | `ckb_Arab` |
| `no`, `nb` | `nob_Latn` |
| `ff` | `fuv_Latn` (Nigerian Fulfulde, not every Fulfulde variety) |

`lu` (Luba-Katanga) is omitted. `lua_Latn` is Luba-Kasai, a different language, and is not used as a substitute.

## Configuration (env vars)

| Var | Default | Notes |
|---|---|---|
| `NLLB_MODEL_NAME` | `facebook/nllb-200-1.3B` | Any NLLB-200 checkpoint, e.g. `facebook/nllb-200-distilled-600M` for a smaller/faster/lower-quality model. |
| `NLLB_MODEL_REVISION` | `b0de46b488af0cf31749cd8da5ed3171e11b2309` | Hugging Face snapshot. Changing it uses a new cache directory. |
| `NLLB_QUANTIZATION` | `int8` | CTranslate2 quantization; `int8` is the practical choice for CPU. |
| `NLLB_CACHE_DIR` | `/models` | Base dir for the HF cache + converted CTranslate2 model (mount a volume here). |
| `NLLB_DEVICE` | `cpu` | Set to `cuda` only if the container actually has GPU access. |
| `NLLB_INTER_THREADS` / `NLLB_INTRA_THREADS` | `1` / `min(4, cpu_count)` | CTranslate2 batch/intra-op parallelism. |
| `NLLB_BEAM_SIZE` | `4` | Decoding beam size (quality/speed trade-off). |
| `NLLB_MAX_DECODING_LENGTH` | `512` | Max output tokens per segment. Hitting it sets `truncated: true`. |
| `NLLB_MAX_SEGMENT_CHARS` | `600` | Long inputs are split into segments of about this size before decoding. |
| `NLLB_CT2_BATCH_SIZE` | `16` | Segments per CTranslate2 call. |
| `NLLB_MAX_BATCH_ITEMS` | `256` | Rejects (`413`) larger `/api/translate/batch` bodies. |
| `NLLB_MAX_INPUT_CHARS` | `4000` | Rejects (`422`) inputs longer than this. |
| `NLLB_SIDECAR_API_KEY` | _(unset)_ | If set, `/api/translate*` and `/languages` require header `x-api-key`. Unset logs a warning. |
| `NLLB_DISABLE_MODEL_LOAD` | `false` | Test-only: skip model download/load entirely (routes still work, always `503`). |

## Testing without the full model

`tests/test_app.py` exercises routing, language resolution, and placeholder protection with
`NLLB_DISABLE_MODEL_LOAD=true`, so it runs fast and does not need `torch`/`ctranslate2`/`transformers`
installed. Real end-to-end translation quality is a manual check (see "Running it" above) -- it is not
part of the automated test suite because it needs the multi-GB model.
