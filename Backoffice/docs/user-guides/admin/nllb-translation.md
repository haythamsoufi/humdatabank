# NLLB translation (admin guide)

Use this guide when you want machine translation beyond the hosted IFRC/Azure engine, or you want official terminology to survive auto-translate.

NLLB does **not** learn from documents you upload. The model weights stay fixed. What you can teach the platform is the **glossary**: approved source/target terms that auto-translate must use. Knowledge Base files are one way to *propose* those terms. They do not retrain NLLB, and they do not by themselves change the chatbot.

## What NLLB is

NLLB (No Language Left Behind) is a self-hosted translation engine. It runs in its own service next to the Backoffice. No translation text is sent to Azure or Google when you select it.

The hosted IFRC/Azure engine stays the default. NLLB appears in the auto-translate service list only after an operator sets `NLLB_SIDECAR_URL`. Until that health check is green, the **NLLB** choice stays disabled.

Selecting **NLLB** means that request uses NLLB only. If NLLB is down, the page reports that it is unavailable. It does not quietly fill the fields with Azure output.

If you leave the service on the default, Azure runs first. NLLB is used only as a fallback, and only for languages Azure cannot translate (for example Akan, Wolof, Oromo, Tajik). Those languages are offered for machine translation only when the sidecar is configured.

## What changes the output, and what does not

| Action | Effect |
|---|---|
| Select **NLLB** in an auto-translate dialog | That translation is produced by NLLB |
| Add or accept a glossary term | Later auto-translate calls keep the English term long enough to set word order, then swap in your official target wording |
| **Seed glossary** | Copies Indicator Bank names, sectors, units, and Common Words into the glossary. Existing terms are left as they are |
| Upload a file to the AI Knowledge Base | Makes that file available to the chatbot and to terminology mining. It does not change NLLB |
| **Mark as same publication**, then **Mine terminology** | Proposes glossary candidates from parallel language versions of one publication |
| Approve a string on Manage translations, or in the in-page review tool | That human text is kept. A later auto-translate run skips it |
| Edit a glossary term | The next translation reapplies the new official form, including on a cached sentence |

Uploading more PDFs, clicking auto-translate again, or chatting with the assistant does not fine-tune the model.

The model weights are Meta's NLLB-200 1.3B checkpoint under the **CC-BY-NC 4.0** license (non-commercial, with attribution). Operators pin a specific model revision; the service does not pick up a newer snapshot by itself.

## Choose the engine in the UI

Auto-translate dialogs (form builder, indicator bank, manage translations, organization names, and similar tools) include a service picker.

1. Open the translate action on the screen you are editing.
2. Choose **NLLB** when you want the self-hosted engine, including for French, Spanish, Arabic, Russian, Chinese, or Hindi.
3. Leave the default (**Hosted translation API**) when you want Azure for languages it supports.
4. Run the translation and read the result before you save. The response records the engine that actually produced the text.

A large batch (many catalog strings at once) can take a few minutes on CPU. A result that would have been cut off mid-sentence is discarded instead of saved as a complete translation. Split very long definitions into shorter sentences and run them again if a field comes back empty.

## Languages and written forms

Plain language codes use one written form:

| Code you send | NLLB writes | To get the other form |
|---|---|---|
| `zh` | Simplified Chinese | `zh_Hant`, `zh_TW`, or `zh_HK` |
| `sr` | Serbian Cyrillic | `sr_Latn` for Latin Serbian |
| `ku` | Kurmanji (Latin) | `ckb` or `ku_Arab` for Sorani |
| `no` and `nb` | Norwegian Bokmål | `nn` for Nynorsk |
| `ff` | Nigerian Fulfulde | There is no separate control for other Fulfulde varieties |

Luba-Katanga (`lu`) is not translated. NLLB has no Luba-Katanga model, and it must not be sent through a different Luba language.

Languages with no engine (for example Romansh) stay in the source language.

## Build the glossary admins actually use

Auto-translate reads approved rows in the glossary. It does not read the Knowledge Base at translation time.

### 1. Seed what the platform already knows

On **Manage translations** (`/admin/translations/manage`), use **Seed glossary**.

That adds must-terms from Indicator Bank names, sectors, units, SPEF, and Common Words. Terms you have already approved are not overwritten. Run this once when you start, and again after a large Indicator Bank import.

### 2. Add a term by hand

Open **Translation quality** (`/admin/translations/quality`) and the **Glossary** tab.

1. Click **Add glossary term**.
2. Enter the English source exactly as it appears in the text you translate (for example `Focal Point` or `National Society`).
3. Enter the official translation for one language.
4. Save.

Use a short official term, not a whole sentence. The engine still translates the sentence; the glossary replaces that term afterwards.

Edit a term in the same grid when the official wording changes. Deactivate a term to stop forcing it.

### 3. Propose terms from parallel documents

Use this when you have the same publication in English and in a target language (a manual, a strategy, a data-guidance chapter).

1. Open **AI Knowledge Base** (`/admin/ai/knowledge-base`).
2. Upload each language version, or import it from Document Management, and wait until processing completes.
3. Select the completed files that are the same publication.
4. Click **Mark as same publication**. This only records that the files belong together. It does not build a sentence-by-sentence translation memory.
5. Click **Mine terminology**.

Mining looks for shared acronyms, then asks the configured OpenAI model to pair English heads with wording that actually appears in the target document. Nothing is added to the live glossary yet.

6. Open **Translation quality** and the **Inbox** tab.
7. Accept a candidate to make it an official term. If it conflicts with a term you already approved, accepting it replaces the official form. Reject candidates that are descriptive phrases, names of people, or the wrong sense of a word.

Repeat with more parallel documents when you want a wider glossary. Each accepted term is what later NLLB and Azure translations must use. The documents themselves stay in the Knowledge Base for the chatbot; see [AI Knowledge Base and embeddings](ai-document-library-and-embeddings.md).

### 4. Review what the machine wrote

On **Manage translations**, machine suggestions are stored as machine translations. Strings a person has approved are skipped the next time you auto-translate.

On **Translation quality**, the **Unreviewed** tab lists machine strings that still need a person. The in-page review tool (the floating translator control on live screens) is the same kind of check, for people who have review access for that language.

Approving a string does not train NLLB. It stops the next auto-translate from replacing that string, and it gives reviewers a clean queue.

## How a single translation is assembled

1. Placeholders such as `[variable]`, `%(name)s`, and Jinja `{{ }}` are masked so the engine cannot rewrite them.
2. The selected engine translates the remaining words. NLLB splits long text into sentences so it is less likely to stop mid-paragraph.
3. Placeholders are restored.
4. Glossary terms found in the English source are swapped to the official target form.
5. The finished string is cached per engine. The next identical request reuses it, then reapplies the current glossary.

If you change a glossary term, you do not need to clear a cache by hand. The next translation of a sentence that contains that term is updated.

## When something looks wrong

- **NLLB is missing from the list.** The sidecar URL is not configured, or this Backoffice process was started before it was set.
- **NLLB is in the list but disabled.** The model is still downloading or converting (first start can take a long time), or the service failed its health check. Wait until **NLLB** is enabled. Do not expect Azure text while it is the selected engine.
- **The request says the service is unavailable.** A health check has already failed. Fix the sidecar, refresh the service list, and try again. Another engine is not substituted.
- **A long field comes back empty.** The output would have been cut off. Shorten the source and translate again.
- **A term is still the everyday word, not the house term.** Add or accept that pair on Translation quality. The English source must match the words in the sentence.
- **Luba-Katanga stays in English.** That is expected. Translate it by hand.
- **Chinese, Serbian, or Kurdish is the wrong script.** The plain code uses the default in the table above. There is no separate picker in the form builder for Traditional Chinese or Latin Serbian.

Operators: install and configure the service with [the NLLB sidecar README](../../../../services/nllb-sidecar/README.md). Quality scores against a human gold set are an engineering check (`Backoffice/scripts/i18n/eval_translation_engines.py`). The shipped gold file is empty on purpose. Do not treat it as a measured comparison until people have filled at least 300 references per language.

## Related

- [Indicator Bank](indicator-bank.md)
- [AI Knowledge Base and embeddings](ai-document-library-and-embeddings.md)
