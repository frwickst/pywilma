"""Tests for unread messages detection."""

from unittest.mock import AsyncMock, patch

import pytest

from wilhelmina.client import WilmaClient, WilmaError


@pytest.mark.asyncio
@patch("wilhelmina.client._has_playwright", True)
@patch("wilhelmina.client.async_playwright")
async def test_get_unread_message_ids(mock_playwright) -> None:
    """Test getting unread message IDs with Playwright."""
    # Initialize client
    client = WilmaClient("https://test.inschool.fi")
    client.user_id = "!12345"
    client._sid = "test_sid"
    client.headless = True

    # Setup Playwright mocks
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_response = AsyncMock()

    # Setup the mock playwright structure
    mock_playwright_instance = AsyncMock()
    mock_playwright.return_value.__aenter__.return_value = mock_playwright_instance
    mock_playwright_instance.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    # Setup the page goto response
    mock_response.status = 200
    mock_page.goto.return_value = mock_response

    # Create a sample HTML response with message rows
    html_content = """
    <!DOCTYPE html>
    <html>
    <body>
        <table id="message-list-table">
            <tbody>
                <tr>
                    <td></td>
                    <td>Unread</td>
                    <td></td>
                    <td></td>
                    <td><input type="checkbox" name="mid" value="123"></td>
                </tr>
                <tr>
                    <td></td>
                    <td></td>
                    <td></td>
                    <td></td>
                    <td><input type="checkbox" name="mid" value="456"></td>
                </tr>
                <tr>
                    <td></td>
                    <td>Unread</td>
                    <td></td>
                    <td></td>
                    <td><input type="checkbox" name="mid" value="789"></td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """
    mock_page.content.return_value = html_content

    # Call the method
    unread_message_ids = await client._get_unread_message_ids()

    # Verify the results
    assert unread_message_ids == {123, 789}

    # Verify the correct methods were called
    mock_playwright_instance.chromium.launch.assert_called_once_with(headless=True)
    mock_browser.new_context.assert_called_once()
    mock_context.new_page.assert_called_once()
    mock_page.goto.assert_called_once_with("https://test.inschool.fi/!12345/messages")
    mock_page.wait_for_selector.assert_called_once_with(
        "table#message-list-table", state="attached", timeout=10000
    )
    mock_page.content.assert_called_once()
    mock_browser.close.assert_called_once()


@pytest.mark.asyncio
@patch("wilhelmina.client._has_playwright", True)
@patch("wilhelmina.client.async_playwright")
async def test_get_unread_message_ids_failure(mock_playwright) -> None:
    """Test error handling in getting unread message IDs."""
    # Initialize client
    client = WilmaClient("https://test.inschool.fi")
    client.user_id = "!12345"
    client._sid = "test_sid"

    # Setup Playwright mocks
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_response = AsyncMock()

    # Setup the mock playwright structure
    mock_playwright_instance = AsyncMock()
    mock_playwright.return_value.__aenter__.return_value = mock_playwright_instance
    mock_playwright_instance.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    # Setup the page goto response with error status
    mock_response.status = 404  # Not found
    mock_page.goto.return_value = mock_response

    # Call the method, should raise an error
    with pytest.raises(WilmaError, match="Failed to load messages page"):
        await client._get_unread_message_ids()

    # Verify the browser was closed
    mock_browser.close.assert_called_once()


@pytest.mark.asyncio
@patch("wilhelmina.client._has_playwright", False)
async def test_get_unread_message_ids_no_playwright() -> None:
    """Test behavior when Playwright is not available."""
    # Initialize client
    client = WilmaClient("https://test.inschool.fi")
    client.user_id = "!12345"
    client._sid = "test_sid"

    # With _has_playwright=False, should return an empty set without errors
    unread_message_ids = await client._get_unread_message_ids()
    assert unread_message_ids == set()


@pytest.mark.asyncio
@patch("wilhelmina.client._has_playwright", True)
@patch("wilhelmina.client.async_playwright")
async def test_get_unread_message_ids_invalid_values(mock_playwright) -> None:
    """Test handling of invalid message IDs."""
    # Initialize client
    client = WilmaClient("https://test.inschool.fi")
    client.user_id = "!12345"
    client._sid = "test_sid"

    # Setup Playwright mocks
    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_response = AsyncMock()

    # Setup the mock playwright structure
    mock_playwright_instance = AsyncMock()
    mock_playwright.return_value.__aenter__.return_value = mock_playwright_instance
    mock_playwright_instance.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    # Setup the page goto response
    mock_response.status = 200
    mock_page.goto.return_value = mock_response

    # Create a sample HTML response with invalid message IDs
    html_content = """
    <!DOCTYPE html>
    <html>
    <body>
        <table id="message-list-table">
            <tbody>
                <tr>
                    <td></td>
                    <td>Unread</td>
                    <td></td>
                    <td></td>
                    <td><input type="checkbox" name="mid" value="invalid"></td>
                </tr>
                <tr>
                    <td></td>
                    <td>Unread</td>
                    <td></td>
                    <td></td>
                    <td><input type="checkbox" name="mid"></td>
                </tr>
                <tr>
                    <td></td>
                    <td>Unread</td>
                    <td></td>
                    <td></td>
                    <td></td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """
    mock_page.content.return_value = html_content

    # Call the method - should handle invalid IDs gracefully
    unread_message_ids = await client._get_unread_message_ids()

    # Should return an empty set since all IDs were invalid
    assert unread_message_ids == set()
    mock_browser.close.assert_called_once()
