"""
IFRC Translation API Service

This module provides integration with the IFRC Translation API for the platform.
It can be used as an additional translation service option in the auto_translator.py system.

API Endpoint: https://ifrc-translationapi-staging.azurewebsites.net/api/translate
Supported Languages: English, French, Spanish, Arabic, Chinese, Russian, Hindi
"""

import json
import logging
import requests
from typing import List, Optional
from .auto_translator import TranslationService

logger = logging.getLogger(__name__)


class IFRCTranslationService(TranslationService):
    """IFRC Translation API service"""

    def __init__(self, api_key: Optional[str] = None, base_url: str = "https://ifrc-translationapi-staging.azurewebsites.net"):
        super().__init__(api_key)
        self.service_name = "ifrc"
        self.base_url = base_url.rstrip('/')
        self.api_endpoint = f"{self.base_url}/api/translate"

        # API key must be provided via environment variable or constructor
        # SECURITY: Never hardcode API keys in source code
        if not self.api_key:
            import os
            self.api_key = os.environ.get('IFRC_TRANSLATE_API_KEY')
            if not self.api_key:
                logger.warning("IFRC Translation API key not configured. Set IFRC_TRANSLATE_API_KEY environment variable.")

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
                response_data = response.json()

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
            else:
                logger.error(f"IFRC API error for '{text}': Status {response.status_code}, Response: {response.text}")

        except requests.exceptions.RequestException as e:
            logger.error(f"IFRC API request failed for '{text}': {e}")
        except json.JSONDecodeError as e:
            logger.error(f"IFRC API JSON decode error for '{text}': {e}")
        except Exception as e:
            logger.error(f"IFRC API unexpected error for '{text}': {e}", exc_info=True)

        return None

    def translate_batch(self, texts: List[str], target_language: str, source_language: str = 'en') -> List[Optional[str]]:
        """Translate multiple texts using IFRC Translation API"""
        if not texts:
            return []

        results = []
        for text in texts:
            result = self.translate_text(text, target_language, source_language)
            results.append(result)
            # Add small delay to be respectful to the API
            import time
            time.sleep(0.1)

        return results

    def test_connection(self) -> bool:
        """Test the connection to the IFRC Translation API"""
        try:
            test_payload = {
                "Text": "test",
                "From": "en",
                "To": "es"
            }

            response = requests.post(
                self.api_endpoint,
                headers=self.headers,
                data=json.dumps(test_payload),
                timeout=10
            )

            if response.status_code == 200:
                response_data = response.json()
                if isinstance(response_data, list) and len(response_data) > 0:
                    logger.info("IFRC Translation API connection test successful")
                    return True
                else:
                    logger.warning("IFRC Translation API connection test failed: Unexpected response format")
                    return False
            else:
                logger.warning(f"IFRC Translation API connection test failed: Status {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"IFRC Translation API connection test failed: {e}", exc_info=True)
            return False

    def get_supported_languages(self) -> List[str]:
        """Get list of supported language codes"""
        return ['en', 'es', 'fr', 'ar', 'zh', 'ru', 'hi']

    def get_service_info(self) -> dict:
        """Get information about the IFRC Translation service"""
        return {
            'name': 'IFRC Translation API',
            'service_name': self.service_name,
            'base_url': self.base_url,
            'supported_languages': self.get_supported_languages(),
            'has_api_key': bool(self.api_key),
            'connection_status': self.test_connection()
        }


def create_ifrc_translation_service(api_key: Optional[str] = None, base_url: str = None) -> IFRCTranslationService:
    """Factory function to create an IFRC Translation service instance"""
    if base_url:
        return IFRCTranslationService(api_key, base_url)
    else:
        return IFRCTranslationService(api_key)


# Convenience functions for direct use
def translate_with_ifrc(text: str, target_language: str, source_language: str = 'en',
                       api_key: Optional[str] = None) -> Optional[str]:
    """Translate text using IFRC Translation API directly"""
    service = IFRCTranslationService(api_key)
    return service.translate_text(text, target_language, source_language)


def translate_batch_with_ifrc(texts: List[str], target_language: str, source_language: str = 'en',
                             api_key: Optional[str] = None) -> List[Optional[str]]:
    """Translate multiple texts using IFRC Translation API directly"""
    service = IFRCTranslationService(api_key)
    return service.translate_batch(texts, target_language, source_language)


def test_ifrc_api_connection(api_key: Optional[str] = None) -> bool:
    """Test the connection to the IFRC Translation API"""
    service = IFRCTranslationService(api_key)
    return service.test_connection()


if __name__ == "__main__":
    # Test the service when run directly
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    logger.info("Testing IFRC Translation API Service...")

    # Test connection
    if test_ifrc_api_connection():
        logger.info("Connection test passed")

        # Test basic translation
        result = translate_with_ifrc("Hello world", "es", "en")
        if result:
            logger.info("Translation test passed: 'Hello world' -> '%s'", result)
        else:
            logger.error("Translation test failed")

        # Test batch translation
        texts = ["Hello", "World", "Test"]
        results = translate_batch_with_ifrc(texts, "es", "en")
        if results and any(results):
            logger.info("Batch translation test passed: %s", results)
        else:
            logger.error("Batch translation test failed")
    else:
        logger.error("Connection test failed")
        sys.exit(1)
