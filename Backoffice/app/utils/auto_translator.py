"""
Automatic Translation Utility

This module provides automatic translation functionality for the platform.
It supports multiple translation services and can be used in translation modals and other places.

Supported languages: English, French, Spanish, Arabic, Chinese, Russian, Hindi
"""

import os
import json
import logging
import requests
import re
from typing import Dict, List, Optional, Union, Tuple
from flask import current_app
import time

logger = logging.getLogger(__name__)

# Language mapping for different translation services
from config import Config

# Reverse mapping for display purposes
LANGUAGE_DISPLAY_NAMES = Config.LANGUAGE_DISPLAY_NAMES


def _normalize_language_code(lang: Optional[Union[str, object]], *, default: str = "en") -> str:
    """
    Normalize a language identifier into a base ISO-ish language code.

    Accepts:
    - ISO codes: 'es', 'ar', 'fr', 'zh'
    - Locale variants: 'es_ES', 'ar-SA'
    - Display/model keys: 'Spanish', 'spanish', 'arabic'

    Always returns a lowercase 2-3 letter code when possible; otherwise returns `default`.
    """
    if lang is None:
        return default

    s = str(lang).strip()
    if not s:
        return default

    s_norm = s.replace("-", "_").strip().lower()
    base = s_norm.split("_", 1)[0].strip().lower()
    if not base:
        return default

    # Direct ISO-ish code
    if re.match(r"^[a-z]{2,3}$", base):
        return base

    # Build a small alias map from config so callers can pass "spanish"/"arabic"/"Spanish".
    # (We keep this local and cheap; Config mappings are static.)
    aliases: Dict[str, str] = {}
    try:
        for code, name in (getattr(Config, "LANGUAGE_DISPLAY_NAMES", {}) or {}).items():
            if code and name:
                aliases[str(name).strip().lower()] = str(code).strip().lower()
        for code, key in (getattr(Config, "LOCALE_TO_TRANSLATION_KEY", {}) or {}).items():
            if code and key:
                aliases[str(key).strip().lower()] = str(code).strip().lower()
        for code, key in (getattr(Config, "LANGUAGE_MODEL_KEY", {}) or {}).items():
            if code and key:
                aliases[str(key).strip().lower()] = str(code).strip().lower()
    except Exception as e:
        logger.debug("_normalize_language_code: alias map failed: %s", e)
        aliases = {}

    resolved = aliases.get(base) or aliases.get(s_norm)
    if resolved and re.match(r"^[a-z]{2,3}$", resolved):
        return resolved

    return default


def _is_meaningful_after_protection(protected_text: str, token_map: Dict[str, str]) -> bool:
    """
    Return True if there's meaningful text left after placeholder protection.

    This avoids calling external services on strings that are only placeholders/punctuation.
    """
    if not protected_text:
        return False

    probe = protected_text
    for token in (token_map or {}).keys():
        probe = probe.replace(token, "")
    probe = probe.strip()
    if not probe:
        return False
    if all(c in ".,:;!?()[]{}" for c in probe):
        return False
    # Numeric/symbol-only strings (e.g. "<5", "50+", "2024-2025") are language-neutral.
    # Treat them as non-meaningful for translation and keep source text as-is.
    if not any(ch.isalpha() for ch in probe):
        return False
    return True


def _is_likely_untranslated_output(
    *,
    translated_text: str,
    protected_text: str,
    token_map: Dict[str, str],
    source_code: str,
    target_code: str,
) -> bool:
    """
    Heuristic: detect when a service "translated" but returned the same English sentence.

    This is common with some LibreTranslate deployments and results in bogus ES/AR
    translations being saved (identical to English).

    We keep this conservative to avoid blocking legitimate unchanged outputs like:
    - acronyms (IFRC, GPS)
    - proper nouns (person/organization names)
    - very short strings ("OK", "SMS")
    """
    if not translated_text or not protected_text:
        return False
    if source_code == target_code:
        return False

    # Only consider "unchanged" (after protection) as suspicious.
    if translated_text != protected_text:
        return False

    # Remove protected placeholder tokens before analyzing the actual text.
    probe = protected_text
    for token in (token_map or {}).keys():
        probe = probe.replace(token, "")
    probe = re.sub(r"\s+", " ", probe).strip()

    if not probe:
        return False

    # Short strings are often legitimately unchanged.
    if len(probe) < 18:
        return False

    # If the text contains acronym-like ALLCAPS tokens, it's often acceptable for ES/AR
    # to keep it unchanged (or partially unchanged) rather than forcing a failure.
    # Example: "HNS and IFRC Secretariat" may legitimately keep "HNS" and "IFRC".
    acronyms = re.findall(r"\b[A-Z]{2,}\b", probe)
    if len(acronyms) >= 2:
        return False

    # If it's a multi-word English-looking sentence and the target is non-English, it's likely a failure.
    latin_words = re.findall(r"[A-Za-z]{2,}", probe)
    if len(latin_words) >= 4:
        return True

    return False


def _debug_translation_enabled() -> bool:
    """
    Enable verbose translation debug logs.

    Set env var AUTO_TRANSLATE_DEBUG=true (only true/false accepted).
    """
    try:
        return str(os.getenv("AUTO_TRANSLATE_DEBUG") or "").strip().lower() == "true"
    except Exception as e:
        logger.debug("AUTO_TRANSLATE_DEBUG env check failed: %s", e)
        return False

class TranslationService:
    """Base class for translation services"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.service_name = "base"

    def translate_text(self, text: str, target_language: str, source_language: str = 'en') -> Optional[str]:
        """Translate text to target language"""
        raise NotImplementedError

    def translate_batch(self, texts: List[str], target_language: str, source_language: str = 'en') -> List[Optional[str]]:
        """Translate multiple texts to target language"""
        raise NotImplementedError

class GoogleTranslateService(TranslationService):
    """Google Translate API service"""

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(api_key)
        self.service_name = "google"
        self.base_url = "https://translation.googleapis.com/language/translate/v2"

    def translate_text(self, text: str, target_language: str, source_language: str = 'en') -> Optional[str]:
        """Translate text using Google Translate API"""
        if not self.api_key:
            logger.warning("Google Translate API key not configured")
            return None

        try:
            params = {
                'key': self.api_key,
                'q': text,
                'target': target_language,
                'source': source_language
            }

            response = requests.post(self.base_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            if 'data' in data and 'translations' in data['data']:
                return data['data']['translations'][0]['translatedText']

        except Exception as e:
            logger.error(f"Google Translate API error: {e}")

        return None

    def translate_batch(self, texts: List[str], target_language: str, source_language: str = 'en') -> List[Optional[str]]:
        """Translate multiple texts using Google Translate API"""
        if not self.api_key:
            logger.warning("Google Translate API key not configured")
            return [None] * len(texts)

        try:
            params = {
                'key': self.api_key,
                'target': target_language,
                'source': source_language
            }

            # Google Translate API supports multiple texts in one request
            for i, text in enumerate(texts):
                params[f'q[{i}]'] = text

            response = requests.post(self.base_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            if 'data' in data and 'translations' in data['data']:
                return [translation['translatedText'] for translation in data['data']['translations']]

        except Exception as e:
            logger.error(f"Google Translate API batch error: {e}")

        return [None] * len(texts)

class LibreTranslateService(TranslationService):
    """LibreTranslate service (free, self-hosted option)"""

    # After a connection failure, stop retrying the host for this many seconds.
    _CIRCUIT_OPEN_COOLDOWN_SECONDS: int = 300  # 5 minutes

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://libretranslate.com"):
        super().__init__(api_key)
        self.service_name = "libre"
        self.base_url = base_url.rstrip('/')
        # Cache supported languages to avoid calling /languages repeatedly during bulk operations.
        self._supported_languages: Optional[set[str]] = None
        self._supported_languages_fetched_at: float = 0.0
        self._supported_languages_ttl_seconds: float = 60 * 60  # 1 hour
        # Circuit breaker: timestamp until which all calls short-circuit to None.
        self._circuit_open_until: float = 0.0

    def _is_circuit_open(self) -> bool:
        """Return True if the host was recently unreachable and we should not retry."""
        return time.time() < self._circuit_open_until

    def _trip_circuit(self) -> None:
        """Mark the host as unreachable for the cooldown period."""
        self._circuit_open_until = time.time() + self._CIRCUIT_OPEN_COOLDOWN_SECONDS
        logger.debug(
            "LibreTranslate circuit open for %ds (host unreachable at %s)",
            self._CIRCUIT_OPEN_COOLDOWN_SECONDS,
            self.base_url,
        )

    def _get_supported_languages(self) -> Optional[set[str]]:
        """
        Best-effort fetch of supported languages from LibreTranslate (/languages).

        Returns:
        - set({...}) of language codes when available
        - None if unknown/unavailable (we then assume "maybe supported" and try anyway)
        """
        # Don't even try to fetch languages when running against known-disabled localhost defaults.
        if self.base_url in ("http://localhost:5000", "http://127.0.0.1:5000"):
            return None

        now = time.time()
        if (
            self._supported_languages is not None
            and self._supported_languages_fetched_at
            and (now - self._supported_languages_fetched_at) < self._supported_languages_ttl_seconds
        ):
            return self._supported_languages

        try:
            resp = requests.get(f"{self.base_url}/languages", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # Common response: [{"code":"en","name":"English"}, ...]
            codes: set[str] = set()
            if isinstance(data, list):
                for row in data:
                    if isinstance(row, dict):
                        code = str(row.get("code") or "").strip().lower()
                        code = code.replace("-", "_").split("_", 1)[0]
                        if re.match(r"^[a-z]{2,3}$", code):
                            codes.add(code)
            self._supported_languages = codes or None
            self._supported_languages_fetched_at = now
            return self._supported_languages
        except requests.exceptions.ConnectionError as e:
            logger.debug("LibreTranslate supported languages probe failed (connection refused): %s", e)
            self._supported_languages = None
            self._supported_languages_fetched_at = now
            self._trip_circuit()
            return None
        except Exception as e:
            logger.debug("LibreTranslate supported languages probe failed: %s", e)
            self._supported_languages = None
            self._supported_languages_fetched_at = now
            return None

    def _supports_language(self, code: str) -> bool:
        codes = self._get_supported_languages()
        if not codes:
            return True  # Unknown => optimistic
        return code in codes

    def translate_text(self, text: str, target_language: str, source_language: str = 'en') -> Optional[str]:
        """Translate text using LibreTranslate"""
        # Skip if pointing to localhost:5000 (default port, likely not available)
        # Allow other localhost ports (e.g., 5001 for Docker-mapped port)
        if self.base_url == 'http://localhost:5000' or self.base_url == 'http://127.0.0.1:5000':
            return None

        # Circuit breaker: don't retry a host that just refused connections.
        if self._is_circuit_open():
            return None

        # Normalize language codes
        source_norm = _normalize_language_code(source_language, default="en")
        target_norm = _normalize_language_code(target_language, default="en")

        # If source and target are the same, return None (no translation needed)
        if source_norm == target_norm:
            logger.debug(f"LibreTranslate: Source and target languages are the same ({source_norm}), skipping translation")
            return None

        # If the server publishes supported languages, log when it doesn't list what we need.
        # Do NOT hard-skip here: some deployments have incomplete /languages responses.
        try:
            codes = self._get_supported_languages()
            if codes and (source_norm not in codes or target_norm not in codes):
                logger.info(
                    f"LibreTranslate /languages does not list {source_norm}->{target_norm} "
                    f"(listed={sorted(list(codes))[:30]}...); attempting anyway."
                )
        except Exception as e:
            logger.debug("LibreTranslate: _get_supported_languages check failed: %s", e)

        try:
            def _call_translate(source_code: str, q: str) -> Optional[str]:
                payload = {
                    'q': q,
                    'source': source_code,
                    'target': target_norm,
                    'format': 'text'
                }
                if self.api_key:
                    payload['api_key'] = self.api_key

                # Retry transient failures (rate-limits / upstream flakiness) to reduce "random" misses in bulk runs.
                last_http_error_preview: Optional[str] = None
                for attempt in range(3):
                    response = requests.post(f"{self.base_url}/translate", json=payload, timeout=15)
                    if response.status_code in (429, 502, 503, 504):
                        last_http_error_preview = (response.text or "")[:200]
                        time.sleep(0.6 * (attempt + 1))
                        continue
                    response.raise_for_status()

                    data = response.json()
                    return data.get('translatedText')

                if last_http_error_preview:
                    logger.warning(
                        f"LibreTranslate transient failure after retries ({source_code}->{target_norm}): {last_http_error_preview}"
                    )
                return None

            # First attempt: explicit source language (typical and fastest when correct).
            translated_text = _call_translate(source_norm, text)

            # Some Libre deployments behave better with language auto-detection.
            # If we got unchanged output (or empty), try once more with source="auto".
            if (not translated_text) or (translated_text == text and source_norm != target_norm):
                translated_text2 = _call_translate("auto", text)
                if translated_text2:
                    translated_text = translated_text2

            # Some deployments treat Title Case words as proper nouns and keep them unchanged.
            # If we still got unchanged output, try a lowercase "nudge" once (best-effort).
            if translated_text == text and source_norm != target_norm:
                lowered = str(text).lower()
                if lowered and lowered != text:
                    translated_text3 = _call_translate("auto", lowered)
                    # Only accept if it's not just echoing the lowered input.
                    if translated_text3 and translated_text3 != lowered:
                        translated_text = translated_text3

            return translated_text

        except requests.exceptions.ConnectionError:
            # Host is unreachable — open the circuit breaker to avoid per-string timeouts.
            self._trip_circuit()
            logger.debug(f"LibreTranslate connection error for '{text[:50]}...' — circuit open for {self._CIRCUIT_OPEN_COOLDOWN_SECONDS}s")
            return None
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # Service endpoint doesn't exist, don't log repeatedly
                logger.debug(f"LibreTranslate endpoint not found (404)")
                return None
            logger.warning(f"LibreTranslate HTTP error {e.response.status_code} for '{text[:50]}...': {e.response.text[:200]}")
            return None
        except Exception as e:
            # Log the exception for debugging but don't spam logs
            logger.debug(f"LibreTranslate error for '{text[:50]}...': {e}")
            return None

    def translate_batch(self, texts: List[str], target_language: str, source_language: str = 'en') -> List[Optional[str]]:
        """Translate multiple texts using LibreTranslate"""
        results = []
        for text in texts:
            result = self.translate_text(text, target_language, source_language)
            results.append(result)
        return results


class IFRCTranslationService(TranslationService):
    """IFRC Translation API service"""

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://ifrc-translationapi-staging.azurewebsites.net"):
        super().__init__(api_key)
        self.service_name = "ifrc"
        self.base_url = base_url.rstrip('/')
        self.api_endpoint = f"{self.base_url}/api/translate"

        if not self.api_key:
            raise ValueError("IFRCTranslationService requires a valid API key")

        self.headers = {
            'x-api-key': self.api_key,
            'Content-Type': 'application/json'
        }

    def translate_text(self, text: str, target_language: str, source_language: str = 'en') -> Optional[str]:
        """Translate text using IFRC Translation API"""
        if not text or not text.strip():
            return None

        try:
            payload = {
                "Text": text,
                "From": source_language,
                "To": target_language
            }

            response = requests.post(
                self.api_endpoint,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=30
            )

            if response.status_code == 200:
                # Check if response is JSON before parsing
                content_type = response.headers.get('Content-Type', '').lower()
                if 'application/json' not in content_type:
                    logger.error(f"IFRC API returned non-JSON response for '{text}': Content-Type: {content_type}, Response preview: {response.text[:200]}")
                    return None

                try:
                    response_data = response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"IFRC API JSON decode error for '{text}': {e}. Response preview: {response.text[:200]}")
                    return None

                # IFRC API returns a list with translation data
                if isinstance(response_data, list) and len(response_data) > 0:
                    translation_data = response_data[0]
                    if 'translations' in translation_data and len(translation_data['translations']) > 0:
                        translated_text = translation_data['translations'][0]['text']
                        logger.debug(f"IFRC Translation: '{text}' -> '{translated_text}' ({source_language}->{target_language})")
                        return translated_text
                    else:
                        logger.warning(f"IFRC API: No translation found in response for '{text}'")
                else:
                    logger.warning(f"IFRC API: Unexpected response format for '{text}': {response_data}")
            elif response.status_code == 429:
                # Rate limit exceeded - log and return None gracefully
                logger.warning(f"IFRC API rate limit exceeded for '{text}': Too Many Requests. Response: {response.text[:200]}")
                return None
            else:
                # Check if error response is HTML
                content_type = response.headers.get('Content-Type', '').lower()
                if 'text/html' in content_type:
                    logger.error(f"IFRC API returned HTML error page for '{text}': Status {response.status_code}. This usually indicates an authentication or endpoint issue.")
                else:
                    logger.error(f"IFRC API error for '{text}': Status {response.status_code}, Response: {response.text[:500]}")

        except requests.exceptions.RequestException as e:
            logger.error(f"IFRC API request failed for '{text}': {e}")
        except json.JSONDecodeError as e:
            logger.error(f"IFRC API JSON decode error for '{text}': {e}")
        except Exception as e:
            logger.error(f"IFRC API unexpected error for '{text}': {e}")

        return None

    def translate_batch(self, texts: List[str], target_language: str, source_language: str = 'en') -> List[Optional[str]]:
        """Translate multiple texts using IFRC Translation API"""
        if not texts:
            return []

        results = []
        for text in texts:
            result = self.translate_text(text, target_language, source_language)
            results.append(result)

        return results



class AutoTranslator:
    """Main automatic translation class"""

    def __init__(self, service_name: str = None, api_key: str = None):
        self.services = {}
        self.default_service = None

        # Initialize available services
        self._init_services(service_name, api_key)

    def _init_services(self, service_name: str = None, api_key: str = None):
        """Initialize translation services"""

        # Try to get API key from environment if not provided
        if not api_key:
            api_key = os.getenv('GOOGLE_TRANSLATE_API_KEY') or os.getenv('TRANSLATE_API_KEY')

        # Initialize Google Translate if API key is available
        if api_key:
            self.services['google'] = GoogleTranslateService(api_key)
            self.default_service = 'google'

        # Initialize LibreTranslate (free tier) - DISABLED by default
        # Only enable if explicitly configured with a valid external URL
        libre_api_key = os.getenv('LIBRE_TRANSLATE_API_KEY')
        libre_url = os.getenv('LIBRE_TRANSLATE_URL')

        # Only initialize LibreTranslate if URL is explicitly set and not pointing to localhost:5000
        # Allow other localhost ports (e.g., 5001 for Docker-mapped port when running locally)
        if libre_url and libre_url != 'http://localhost:5000' and libre_url != 'http://127.0.0.1:5000':
            self.services['libre'] = LibreTranslateService(libre_api_key, libre_url)

        # Initialize IFRC Translation API
        ifrc_api_key = os.getenv('IFRC_TRANSLATE_API_KEY')
        ifrc_url = os.getenv('IFRC_TRANSLATE_URL', 'https://ifrc-translationapi-staging.azurewebsites.net')
        if ifrc_api_key:
            self.services['ifrc'] = IFRCTranslationService(ifrc_api_key, ifrc_url)
        else:
            logger.warning("IFRC_TRANSLATE_API_KEY not set; IFRC translation service disabled")

        # Set default service
        if service_name and service_name in self.services:
            self.default_service = service_name
        elif not self.default_service:
            # Prefer IFRC API (official IFRC service), then Google, then LibreTranslate
            if 'ifrc' in self.services:
                self.default_service = 'ifrc'
            elif 'google' in self.services:
                self.default_service = 'google'
            elif 'libre' in self.services:
                self.default_service = 'libre'
            else:
                self.default_service = None

    @staticmethod
    def _protect_variables(text: str) -> Tuple[str, Dict[str, str]]:
        """
        Protect template placeholders so translation services don't alter them.

        We intentionally treat **any balanced bracket expression** as a placeholder:
        - Simple: `[variable]`
        - Nested/expressions: `[[period]+2]`, `[[a]+[b]]`, etc.

        We also protect Python %-format tokens:
        - Named: `%(name)s`, `%(count)d`, `%(value).2f`
        - Positional: `%s`, `%d`, `%.2f`, etc.

        Returns `(protected_text, variable_map)` where `variable_map` is `{token: original}`.
        """
        if not text:
            return text, {}

        token_map: Dict[str, str] = {}
        token_counter = 0

        def make_token() -> str:
            nonlocal token_counter
            # Use an alphanumeric-only token (no underscores/punctuation).
            # Some translation services (especially into RTL scripts like Arabic) may drop or
            # transform tokens that look like "noise". A "word-like" token survives better.
            # Avoid digits as some services localize 0-9 into Arabic-Indic numerals, which would
            # prevent exact restoration. Encode counter as A, B, ..., Z, AA, AB, ...
            n = token_counter
            letters = []
            while True:
                letters.append(chr(ord('A') + (n % 26)))
                n = (n // 26) - 1
                if n < 0:
                    break
            suffix = ''.join(reversed(letters))
            token = f"IFRCPLACEHOLDER{suffix}"
            token_counter += 1
            return token

        # 1) Protect any balanced bracket expressions (supports nested brackets).
        out: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch != '[':
                out.append(ch)
                i += 1
                continue

            start = i
            depth = 0
            j = i
            closed_at: Optional[int] = None
            while j < n:
                if text[j] == '[':
                    depth += 1
                elif text[j] == ']':
                    depth -= 1
                    if depth == 0:
                        closed_at = j
                        break
                j += 1

            if closed_at is None:
                # Unbalanced bracket; treat as literal.
                out.append(ch)
                i += 1
                continue

            original = text[start:closed_at + 1]
            token = make_token()
            token_map[token] = original
            out.append(token)
            i = closed_at + 1

        protected_text = ''.join(out)

        # 2) Protect Python %-format tokens.
        # Named: %(name)s, %(value).2f, %(count)d, etc.
        named_fmt = re.compile(r"%\([^)]+\)[#0\- +]*\d*(?:\.\d+)?[sdfoxX]")
        # Positional: %s, %d, %.2f, etc. (avoid %% and avoid named formats)
        positional_fmt = re.compile(r"%(?!%)(?!\()[#0\- +]*\d*(?:\.\d+)?[sdfoxX]")

        def replace_fmt(match: re.Match) -> str:
            original = match.group(0)
            token = make_token()
            token_map[token] = original
            return token

        protected_text = named_fmt.sub(replace_fmt, protected_text)
        protected_text = positional_fmt.sub(replace_fmt, protected_text)

        return protected_text, token_map

    @staticmethod
    def _restore_variables(text: str, variable_map: Dict[str, str]) -> str:
        """
        Restore protected placeholders into translated text.

        `variable_map` is `{token: original}` created by `_protect_variables`.
        """
        if not text or not variable_map:
            return text

        restored = text

        # Replace longest tokens first (defensive; prevents partial overlaps).
        tokens = sorted(variable_map.keys(), key=len, reverse=True)
        for token in tokens:
            original = variable_map.get(token, '')
            if not original:
                continue
            # Fast path: exact replacement
            restored = restored.replace(token, original)

            # Defensive: some services may inject bidi marks / zero-width chars or whitespace
            # between token characters. Attempt a regex-based restore that tolerates those.
            try:
                # Bidi/zero-width marks commonly seen around RTL text
                zw = r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\u200b\u200c\u200d\s]*"
                # Build pattern that matches token chars with optional marks/spaces between them
                pattern = zw.join(map(re.escape, list(token)))
                restored = re.sub(pattern, original, restored, flags=re.IGNORECASE)
            except Exception as e:
                logger.debug("_restore_protected_variables: bidi restore failed: %s", e)

        # Defensive: if a service HTML-escaped the token, try unescaping and restoring again.
        # (Rare, but cheap to handle.)
        try:
            import html
            unescaped = html.unescape(restored)
            if unescaped != restored:
                restored2 = unescaped
                for token in tokens:
                    original = variable_map.get(token, '')
                    if not original:
                        continue
                    restored2 = restored2.replace(token, original)
                    try:
                        zw = r"[\u200e\u200f\u202a-\u202e\u2066-\u2069\u200b\u200c\u200d\s]*"
                        pattern = zw.join(map(re.escape, list(token)))
                        restored2 = re.sub(pattern, original, restored2, flags=re.IGNORECASE)
                    except Exception as e:
                        logger.debug("_restore_protected_variables: unescape bidi restore failed: %s", e)
                restored = restored2
        except Exception as e:
            logger.debug("_restore_protected_variables: html unescape restore failed: %s", e)

        # Last-resort safety: if a translation service *dropped* the placeholder token entirely,
        # ensure we do not lose variables. Append any missing originals at the end (once).
        try:
            missing: list[str] = []
            for token in tokens:
                original = variable_map.get(token, '')
                if original and original not in restored:
                    missing.append(original)
            if missing:
                # Keep deterministic order based on appearance in original token_map iteration
                restored = (restored.rstrip() + " " + " ".join(missing)).strip()
        except Exception as e:
            logger.debug("_restore_protected_variables: missing vars append failed: %s", e)

        return restored

    def translate_text(self, text: str, target_language: str, source_language: str = 'en',
                      service_name: str = None) -> Optional[str]:
        """Translate a single text, preserving template variables."""
        if not text or not str(text).strip():
            return None

        original_text = str(text)
        protected_text, token_map = self._protect_variables(original_text)

        # Normalize languages to ISO-ish base codes
        target_code = _normalize_language_code(target_language, default="en")
        source_code = _normalize_language_code(source_language, default="en")

        # If protection removed all meaningful text (e.g., text is only placeholders/punctuation),
        # skip calling the translation service to avoid placeholder churn.
        if not _is_meaningful_after_protection(protected_text, token_map):
            return original_text

        if token_map:
            try:
                logger.debug(
                    "AutoTranslator: protected placeholders",
                    extra={"protected_preview": protected_text[:120], "tokens": list(token_map.keys())[:10]},
                )
            except Exception as e:
                logger.debug("AutoTranslator: placeholder debug log failed: %s", e)

        # Build ordered list of services to try.
        #
        # When the caller explicitly names a service (e.g. the user selected IFRC in the
        # auto-translate modal), we use ONLY that service — no automatic fallbacks.
        # Falling back to a different service when one was explicitly chosen silently
        # ignores the user's selection and can produce unexpected results (e.g. trying a
        # dead LibreTranslate instance after IFRC returned an unchanged-but-correct string).
        #
        # When no service is named we use the default, then the rest as fallbacks.
        services_to_try: list[TranslationService] = []

        if service_name:
            requested = (self.services or {}).get(service_name)
            if requested and requested.service_name != 'mock':
                services_to_try = [requested]
            # If the name is invalid fall through to default logic below.

        if not services_to_try:
            default_service = self._get_service()
            if default_service and default_service.service_name != 'mock':
                services_to_try.append(default_service)
            for _, svc in (self.services or {}).items():
                if not svc or getattr(svc, "service_name", None) == 'mock':
                    continue
                if svc not in services_to_try:
                    services_to_try.append(svc)

        debug = _debug_translation_enabled()
        for svc_idx, svc in enumerate(services_to_try):
            try:
                translated = svc.translate_text(protected_text, target_code, source_code)
            except Exception as e:
                logger.warning(f"Translation service {getattr(svc, 'service_name', 'unknown')} failed: {e}")
                continue

            if not translated:
                if debug:
                    logger.info(
                        f"[auto_translate_debug] svc={getattr(svc,'service_name','?')} "
                        f"{source_code}->{target_code} result=None text={original_text[:120]!r}"
                    )
                continue

            # Some services legitimately return unchanged strings (e.g., acronyms/proper nouns).
            # If we have other services available, treat "unchanged" as a soft-failure so we
            # can attempt a better translation; otherwise accept it to avoid hard failures.
            if translated == protected_text and source_code != target_code:
                # If the output is *likely* not a real translation (long English-ish sentence),
                # treat it as a failure even if it's the last service.
                if _is_likely_untranslated_output(
                    translated_text=translated,
                    protected_text=protected_text,
                    token_map=token_map,
                    source_code=source_code,
                    target_code=target_code,
                ):
                    if debug:
                        logger.info(
                            f"[auto_translate_debug] svc={getattr(svc,'service_name','?')} "
                            f"{source_code}->{target_code} rejected=unchanged_englishish text={original_text[:120]!r}"
                        )
                    continue
                is_last_service = (svc_idx >= (len(services_to_try) - 1))
                if not is_last_service:
                    if debug:
                        logger.info(
                            f"[auto_translate_debug] svc={getattr(svc,'service_name','?')} "
                            f"{source_code}->{target_code} softfail=unchanged_try_fallback text={original_text[:120]!r}"
                        )
                    continue

            if debug:
                # Log a short preview (post-restore) for debugging.
                restored_preview = self._restore_variables(translated, token_map)
                logger.info(
                    f"[auto_translate_debug] svc={getattr(svc,'service_name','?')} "
                    f"{source_code}->{target_code} ok text={original_text[:120]!r} out={restored_preview[:120]!r}"
                )
            return self._restore_variables(translated, token_map)

        return None

    def translate_batch(self, texts: List[str], target_language: str, source_language: str = 'en',
                       service_name: str = None) -> List[Optional[str]]:
        """Translate multiple texts, preserving template variables"""
        if not texts:
            return []

        # Normalize languages to ISO-ish base codes
        target_code = _normalize_language_code(target_language, default="en")
        source_code = _normalize_language_code(source_language, default="en")

        # Protect variables for all texts, and pre-decide which ones should not be sent to a service.
        protected_texts: list[str] = []
        variable_maps: list[Dict[str, str]] = []
        originals: list[str] = []
        should_translate: list[bool] = []
        for t in texts:
            original = "" if t is None else str(t)
            protected, vmap = self._protect_variables(original)
            protected_texts.append(protected)
            variable_maps.append(vmap)
            originals.append(original)
            should_translate.append(_is_meaningful_after_protection(protected, vmap))

        # Prepare output list.
        out: list[Optional[str]] = [None] * len(texts)
        for i, ok in enumerate(should_translate):
            if not ok:
                out[i] = originals[i]

        # Build ordered list of services to try (same rules as translate_text).
        # Explicit service_name → only that service, no fallbacks.
        services_to_try: list[TranslationService] = []
        if service_name:
            requested = (self.services or {}).get(service_name)
            if requested and requested.service_name != "mock":
                services_to_try = [requested]

        if not services_to_try:
            default_service = self._get_service()
            if default_service and default_service.service_name != "mock":
                services_to_try.append(default_service)
            for _, svc in (self.services or {}).items():
                if not svc or getattr(svc, "service_name", None) == "mock":
                    continue
                if svc not in services_to_try:
                    services_to_try.append(svc)

        # Try services, filling missing items as we go (per-item fallback).
        for svc_idx, svc in enumerate(services_to_try):
            # Indices that still need translation and should be sent.
            pending = [i for i in range(len(out)) if out[i] is None and should_translate[i]]
            if not pending:
                break

            try:
                batch_inputs = [protected_texts[i] for i in pending]
                batch_results = svc.translate_batch(batch_inputs, target_code, source_code)
            except Exception as e:
                logger.warning(f"Batch translation service {getattr(svc, 'service_name', 'unknown')} failed: {e}")
                continue

            if not batch_results:
                continue

            # Map results back and restore placeholders.
            for idx, translated in enumerate(batch_results):
                i = pending[idx] if idx < len(pending) else None
                if i is None:
                    continue
                if not translated:
                    continue
                # If unchanged and we have more services to try, leave it pending.
                if translated == protected_texts[i] and source_code != target_code:
                    # If it's likely not a real translation (long English-ish sentence), never accept it.
                    if _is_likely_untranslated_output(
                        translated_text=translated,
                        protected_text=protected_texts[i],
                        token_map=variable_maps[i],
                        source_code=source_code,
                        target_code=target_code,
                    ):
                        continue
                    is_last_service = (svc_idx >= (len(services_to_try) - 1))
                    if not is_last_service:
                        continue
                out[i] = self._restore_variables(translated, variable_maps[i])

        return out

    def _get_language_code_from_name(self, language_name: str) -> Optional[str]:
        """Convert language name to language code using Config mapping."""
        if not language_name:
            return None
        needle = str(language_name).strip().lower()
        if not needle:
            return None
        for code, name in Config.LANGUAGE_MODEL_KEY.items():
            try:
                if str(name).strip().lower() == needle:
                    return str(code).strip().lower()
            except Exception as e:
                logger.debug("_get_language_code_from_name: item check failed for %r: %s", code, e)
                continue
        return None

    def _get_language_code(self, lang: str) -> Optional[str]:
        """Get language code from either a code or a name.

        If lang is already a code (key in LANGUAGE_MODEL_KEY), return it.
        Otherwise, try to convert from language name to code.
        """
        if not lang:
            return None

        # Normalize to base ISO code (e.g., fr_FR -> fr)
        lang_norm = str(lang).strip()
        lang_norm = lang_norm.replace("-", "_").split("_", 1)[0].strip().lower()
        if not lang_norm:
            return None

        # Known mapping (legacy/static)
        if lang_norm in Config.LANGUAGE_MODEL_KEY:
            return lang_norm

        # Try to resolve from configured model keys (display names)
        resolved = self._get_language_code_from_name(lang)
        if resolved:
            return resolved

        # Dynamic language support: accept any ISO-ish code even if not in mapping.
        # This enables newly enabled languages (e.g. 'ja') without code changes.
        if re.match(r"^[a-z]{2,3}$", lang_norm):
            return lang_norm

        return None

    def translate_form_item(self, label: str, definition: str = None,
                           target_languages: List[str] = None,
                           service_name: str = None) -> Dict[str, Dict[str, str]]:
        """
        Translate form item (label and definition) to multiple languages

        Returns:
            {
                'label_translations': {'fr': '...', 'es': '...', ...},
                'definition_translations': {'fr': '...', 'es': '...', ...}
            }
        """
        if not target_languages:
            target_languages = [Config.LANGUAGE_MODEL_KEY[code] for code in Config.TRANSLATABLE_LANGUAGES]

        result = {
            'label_translations': {},
            'definition_translations': {}
        }

        # Translate label
        if label and label.strip():
            for lang in target_languages:
                translated_label = self.translate_text(label, lang, 'en', service_name)
                if translated_label:
                    # Get language code (handles both codes and names)
                    lang_code = self._get_language_code(lang)
                    if lang_code:
                        result['label_translations'][lang_code] = translated_label

        # Translate definition
        if definition and definition.strip():
            for lang in target_languages:
                translated_definition = self.translate_text(definition, lang, 'en', service_name)
                if translated_definition:
                    # Get language code (handles both codes and names)
                    lang_code = self._get_language_code(lang)
                    if lang_code:
                        result['definition_translations'][lang_code] = translated_definition

        return result

    def translate_section_name(self, name: str, target_languages: List[str] = None,
                              service_name: str = None) -> Dict[str, str]:
        """
        Translate section name to multiple languages

        Returns:
            {'fr': '...', 'es': '...', ...}
        """
        if not target_languages:
            target_languages = [Config.LANGUAGE_MODEL_KEY[code] for code in Config.TRANSLATABLE_LANGUAGES]

        result = {}

        if name and name.strip():
            for lang in target_languages:
                translated_name = self.translate_text(name, lang, 'en', service_name)
                if translated_name:
                    # Get language code (handles both codes and names)
                    lang_code = self._get_language_code(lang)
                    if lang_code:
                        result[lang_code] = translated_name

        return result

    def translate_question_option(self, option_text: str, target_languages: List[str] = None,
                                 service_name: str = None) -> Dict[str, str]:
        """
        Translate a single question option to multiple languages

        Returns:
            {'fr': '...', 'es': '...', ...}
        """
        if not target_languages:
            target_languages = [Config.LANGUAGE_MODEL_KEY[code] for code in Config.TRANSLATABLE_LANGUAGES]

        result = {}

        if option_text and option_text.strip():
            for lang in target_languages:
                translated_option = self.translate_text(option_text, lang, 'en', service_name)
                if translated_option:
                    # Get language code (handles both codes and names)
                    lang_code = self._get_language_code(lang)
                    if lang_code:
                        result[lang_code] = translated_option

        return result

    def translate_page_name(self, name: str, target_languages: List[str] = None,
                           service_name: str = None) -> Dict[str, str]:
        """
        Translate page name to multiple languages

        Returns:
            {'fr': '...', 'es': '...', ...}
        """
        if not target_languages:
            target_languages = [Config.LANGUAGE_MODEL_KEY[code] for code in Config.TRANSLATABLE_LANGUAGES]

        result = {}

        if name and name.strip():
            for lang in target_languages:
                translated_name = self.translate_text(name, lang, 'en', service_name)
                if translated_name:
                    # Get language code (handles both codes and names)
                    lang_code = self._get_language_code(lang)
                    if lang_code:
                        result[lang_code] = translated_name

        return result

    def translate_template_name(self, name: str, target_languages: List[str] = None,
                              service_name: str = None) -> Dict[str, str]:
        """
        Translate template name to multiple languages

        Returns:
            {'fr': '...', 'es': '...', ...}
        """
        if not target_languages:
            target_languages = [Config.LANGUAGE_MODEL_KEY[code] for code in Config.TRANSLATABLE_LANGUAGES]

        result = {}

        if name and name.strip():
            for lang in target_languages:
                translated_name = self.translate_text(name, lang, 'en', service_name)
                if translated_name:
                    # Get language code (handles both codes and names)
                    lang_code = self._get_language_code(lang)
                    if lang_code:
                        result[lang_code] = translated_name

        return result

    def _get_service(self, service_name: str = None) -> Optional[TranslationService]:
        """Get translation service by name"""
        if service_name and service_name in self.services:
            return self.services[service_name]
        elif self.default_service:
            return self.services[self.default_service]
        elif self.services:
            # Fallback to the first available service
            first_key = next(iter(self.services.keys()))
            return self.services[first_key]
        return None

    def get_available_services(self) -> List[str]:
        """Get list of available translation services"""
        return list(self.services.keys())

    def get_default_service(self) -> str:
        """Get the default translation service name"""
        return self.default_service or 'mock'

    def check_service_status(self, service_name: str = None) -> Dict[str, bool]:
        """Check the status of translation services"""
        status = {}

        if service_name:
            # Check specific service
            service = self._get_service(service_name)
            if service:
                status[service_name] = self._test_service(service)
            return status

        # Check all services
        for name, service in self.services.items():
            status[name] = self._test_service(service)

        return status

    def _test_service(self, service: TranslationService) -> bool:
        """Test if a service is available by making a simple translation request"""
        try:
            # Try to translate a simple test word
            result = service.translate_text("test", "fr", "en")
            return result is not None and len(result.strip()) > 0
        except Exception as e:
            logger.debug(f"Service {service.service_name} test failed: {e}")
            return False

# Global instance
auto_translator = AutoTranslator()

def get_auto_translator() -> AutoTranslator:
    """Get the global auto translator instance"""
    return auto_translator

def translate_text(text: str, target_language: str, source_language: str = 'en',
                  service_name: str = None) -> Optional[str]:
    """Convenience function to translate text"""
    return auto_translator.translate_text(text, target_language, source_language, service_name)

def translate_form_item_auto(label: str, definition: str = None,
                            target_languages: List[str] = None,
                            service_name: str = None) -> Dict[str, Dict[str, str]]:
    """Convenience function to translate form item"""
    return auto_translator.translate_form_item(label, definition, target_languages, service_name)

def translate_section_name_auto(name: str, target_languages: List[str] = None,
                               service_name: str = None) -> Dict[str, str]:
    """Convenience function to translate section name"""
    return auto_translator.translate_section_name(name, target_languages, service_name)

def translate_question_option_auto(option_text: str, target_languages: List[str] = None,
                                  service_name: str = None) -> Dict[str, str]:
    """Convenience function to translate question option"""
    return auto_translator.translate_question_option(option_text, target_languages, service_name)

def translate_page_name_auto(name: str, target_languages: List[str] = None,
                            service_name: str = None) -> Dict[str, str]:
    """Convenience function to translate page name"""
    return auto_translator.translate_page_name(name, target_languages, service_name)

def translate_template_name_auto(name: str, target_languages: List[str] = None,
                               service_name: str = None) -> Dict[str, str]:
    """Convenience function to translate template name"""
    return auto_translator.translate_template_name(name, target_languages, service_name)
