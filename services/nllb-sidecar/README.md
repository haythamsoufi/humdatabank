# NLLB sidecar

Self-hosted machine translation (CTranslate2 + NLLB-200). IFRC/Azure remains the **default**
Backoffice engine. When NLLB is selected in the UI, it translates every mapped language,
including the core seven (`en, fr, es, ar, ru, zh, hi`).

## How it works

- Model: [`facebook/nllb-200-1.3B`](https://huggingface.co/facebook/nllb-200-1.3B) (configurable via
  `NLLB_MODEL_NAME`), quantized to `int8` and served with [CTranslate2](https://github.com/OpenNMT/CTranslate2).
- **No external API calls at request time** -- translation runs entirely inside this container, on CPU.
- On first boot the container downloads the model from Hugging Face and converts it to a CTranslate2
  model (`ct2-transformers-converter --quantization int8`). This takes **10-30+ minutes** and needs
  ~6GB of disk, depending on bandwidth/CPU. The converted model is cached on the `nllb_models` volume
  (`/models` in the container), so subsequent restarts skip straight to loading (a few seconds).
- `/health` reports the real state (`loading` / `ready` / `error`) -- `ok: true` only once the model
  is actually loaded and serving. `/api/translate` returns `503` (with `Retry-After`) while loading,
  rather than silently echoing the source text.

## Running it

```bash
docker compose --profile nllb up -d --build
docker compose logs -f nllb        # watch download/conversion progress
curl http://localhost:9100/health  # {"ok": false, "status": "loading", ...} until ready
```

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

`GET /languages` lists the ISO 639-1 codes this sidecar maps to a FLORES-200 code (see
`ISO1_TO_FLORES200` in `app.py`) -- core languages plus ~115 others. Codes not in that table
return `400`.

## Configuration (env vars)

| Var | Default | Notes |
|---|---|---|
| `NLLB_MODEL_NAME` | `facebook/nllb-200-1.3B` | Any NLLB-200 checkpoint, e.g. `facebook/nllb-200-distilled-600M` for a smaller/faster/lower-quality model. |
| `NLLB_QUANTIZATION` | `int8` | CTranslate2 quantization; `int8` is the practical choice for CPU. |
| `NLLB_CACHE_DIR` | `/models` | Base dir for the HF cache + converted CTranslate2 model (mount a volume here). |
| `NLLB_DEVICE` | `cpu` | Set to `cuda` only if the container actually has GPU access. |
| `NLLB_INTER_THREADS` / `NLLB_INTRA_THREADS` | `1` / `min(4, cpu_count)` | CTranslate2 batch/intra-op parallelism. |
| `NLLB_BEAM_SIZE` | `4` | Decoding beam size (quality/speed trade-off). |
| `NLLB_MAX_DECODING_LENGTH` | `256` | Max output tokens per segment. |
| `NLLB_MAX_INPUT_CHARS` | `4000` | Rejects (`422`) inputs longer than this. |
| `NLLB_SIDECAR_API_KEY` | _(unset)_ | If set, `/api/translate*` require header `x-api-key`. |
| `NLLB_DISABLE_MODEL_LOAD` | `false` | Test-only: skip model download/load entirely (routes still work, always `503`). |

## Testing without the full model

`tests/test_app.py` exercises routing, language resolution, and placeholder protection with
`NLLB_DISABLE_MODEL_LOAD=true`, so it runs fast and does not need `torch`/`ctranslate2`/`transformers`
installed. Real end-to-end translation quality is a manual check (see "Running it" above) -- it is not
part of the automated test suite because it needs the multi-GB model.
