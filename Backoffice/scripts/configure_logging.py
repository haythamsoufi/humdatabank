#!/usr/bin/env python3
"""
Logging Configuration Script for NGO Databank

This script helps configure logging levels for the application.
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)


def set_verbose_form_debug(enabled=True):
    """Set the VERBOSE_FORM_DEBUG environment variable."""
    if enabled:
        os.environ['VERBOSE_FORM_DEBUG'] = 'true'
        logger.info("Verbose form debug logging ENABLED")
        logger.info("   You will now see detailed debug messages for form processing, translations, etc.")
    else:
        os.environ['VERBOSE_FORM_DEBUG'] = 'false'
        logger.info("Verbose form debug logging DISABLED")
        logger.info("   Form processing debug messages will be suppressed for cleaner logs.")

def show_current_status():
    """Show the current logging configuration status."""
    verbose_debug = str(os.environ.get('VERBOSE_FORM_DEBUG', 'false')).strip().lower() == 'true'
    logger.info("Current VERBOSE_FORM_DEBUG setting: %s", verbose_debug)

    if verbose_debug:
        logger.info("Verbose form debug logging is ENABLED")
        logger.info("   - Form processing debug messages: ON")
        logger.info("   - Translation debug messages: ON")
        logger.info("   - API tracking debug messages: ON")
    else:
        logger.info("Verbose form debug logging is DISABLED")
        logger.info("   - Form processing debug messages: OFF")
        logger.info("   - Translation debug messages: OFF")
        logger.info("   - API tracking debug messages: OFF")

def main():
    """Main function to handle command line arguments."""
    if len(sys.argv) < 2:
        logger.info("Usage: python configure_logging.py [enable|disable|status]")
        logger.info("\nCommands:")
        logger.info("  enable   - Enable verbose form debug logging")
        logger.info("  disable  - Disable verbose form debug logging (default)")
        logger.info("  status   - Show current logging configuration")
        return

    command = sys.argv[1].lower()

    if command == 'enable':
        set_verbose_form_debug(True)
    elif command == 'disable':
        set_verbose_form_debug(False)
    elif command == 'status':
        show_current_status()
    else:
        logger.warning("Unknown command: %s", command)
        logger.info("Use: enable, disable, or status")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
