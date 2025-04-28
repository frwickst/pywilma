"""Tests for package __init__."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from wilhelmina import __all__, install_playwright_deps


def test_all_exports() -> None:
    """Test that __all__ contains expected exports."""
    expected = [
        "WilmaClient",
        "WilmaError",
        "AuthenticationError",
        "Message",
        "MessagesList",
        "Sender",
        "install_playwright_deps",
    ]

    for item in expected:
        assert item in __all__


@pytest.mark.parametrize(
    "playwright_exists,force,quiet,expected_return",
    [
        (True, False, False, True),  # Normal case when playwright exists
        (False, False, False, False),  # Skip when playwright doesn't exist
        (False, True, False, False),  # Force but playwright doesn't exist (should still attempt)
        (True, True, True, True),  # Force and quiet
    ],
)
def test_install_playwright_deps(
    playwright_exists: bool, force: bool, quiet: bool, expected_return: bool
) -> None:
    """Test playwright dependency installation."""

    # Mock importlib.util.find_spec
    mock_find_spec = MagicMock()
    mock_find_spec.return_value = MagicMock() if playwright_exists else None

    # Mock subprocess.run
    mock_run = MagicMock()
    if not playwright_exists and not force:
        mock_run.side_effect = None  # Should not be called
    else:
        # When force=True but playwright doesn't exist, simulate failure
        if not playwright_exists and force:
            mock_run.side_effect = subprocess.SubprocessError("Command failed")
        else:
            mock_run.return_value = MagicMock()

    with (
        patch("wilhelmina.__init__.importlib.util.find_spec", mock_find_spec),
        patch("wilhelmina.__init__.subprocess.run", mock_run),
    ):
        result = install_playwright_deps(force=force, quiet=quiet)

        assert result == expected_return

        if not playwright_exists and not force:
            mock_run.assert_not_called()
        else:
            mock_run.assert_called_once()
