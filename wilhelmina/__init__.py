"""Wilma API client."""

import importlib.util
import logging
import subprocess
import sys

from wilhelmina.client import AuthenticationError, WilmaClient, WilmaError
from wilhelmina.models import Message, MessagesList, Sender

logger = logging.getLogger(__name__)

__all__ = [
    "WilmaClient",
    "WilmaError",
    "AuthenticationError",
    "Message",
    "MessagesList",
    "Sender",
    "install_playwright_deps",
]


def install_playwright_deps(force: bool = False, quiet: bool = False) -> bool:
    """Install Playwright dependencies.

    Args:
        force: Force installation even if playwright is not installed
        quiet: Don't log anything

    Returns:
        True if installed, False if skipped or failed
    """
    if not force:
        # Check if playwright is installed
        if importlib.util.find_spec("playwright") is None:
            if not quiet:
                logger.warning(
                    "Playwright is not installed. Install with 'pip install wilma[playwright]'"
                )
            return False

    log_level = logging.ERROR if quiet else logging.INFO
    logger.setLevel(log_level)

    try:
        logger.info("Installing Playwright dependencies...")
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=quiet,
        )
        logger.info("Playwright dependencies installed successfully.")
        return True
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.exception("Failed to install Playwright dependencies: %s", e)
        return False


# Auto-install Playwright browser when package is installed with the extra
if importlib.util.find_spec("playwright") is not None:
    # Only attempt installation during import if playwright is available
    # This ensures the browser is installed automatically when the package
    # is installed with the playwright extra
    install_playwright_deps(quiet=True)
