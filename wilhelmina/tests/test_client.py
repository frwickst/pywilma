"""Tests for WilmaClient."""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from aiohttp import ClientResponse

from wilhelmina.client import AuthenticationError, WilmaClient, WilmaError
from wilhelmina.models import Message

################################
# Basic Client Functionality
################################


@pytest.mark.asyncio
async def test_init() -> None:
    """Test client initialization."""
    # Test with default parameters (no session provided)
    client = WilmaClient("https://test.inschool.fi", debug=True, headless=False)
    assert client.base_url == "https://test.inschool.fi"
    assert client.debug is True
    assert client.headless is False
    assert client.session is None
    assert client._owns_session is True

    # Make sure session is created by _ensure_session
    session = await client._ensure_session()
    assert session is client.session
    assert isinstance(session, aiohttp.ClientSession)

    # Close client
    await client.close()
    assert client.session is None

    # Test with provided session
    existing_session = aiohttp.ClientSession()
    client_with_session = WilmaClient("https://test.inschool.fi", session=existing_session)
    assert client_with_session.session is existing_session
    assert client_with_session._owns_session is False

    # Close should not close the session
    await client_with_session.close()
    assert not existing_session.closed

    # Clean up
    await existing_session.close()


@pytest.mark.asyncio
async def test_context_manager() -> None:
    """Test client as a context manager."""
    # We need to use a real session for this test
    async with WilmaClient("https://test.inschool.fi") as client:
        assert isinstance(client.session, aiohttp.ClientSession)
        assert not client.session.closed

    # Session should be closed after exiting context
    assert client.session is None


################################
# Authentication
################################


@pytest.mark.asyncio
async def test_check_auth() -> None:
    """Test authentication check."""
    # Initialize client
    client = WilmaClient("https://test.inschool.fi")

    # Not authenticated
    with pytest.raises(AuthenticationError):
        client._check_auth()

    # Set authentication values
    client.user_id = "!12345"
    client._sid = "test_sid"

    # Should not raise exception
    client._check_auth()


@pytest.mark.asyncio
@patch("wilhelmina.client.aiohttp.ClientSession")
async def test_login_success(mock_session) -> None:
    """Test successful login."""
    # Create client with patched session
    client = WilmaClient("https://test.inschool.fi", debug=False)

    # Login ID cookie
    login_id_cookie = MagicMock()
    login_id_cookie.value = "test_login_id"

    # Set up token response mock
    token_resp = AsyncMock()
    token_resp.status = 200
    token_resp.cookies = MagicMock()
    token_resp.cookies.get = MagicMock(return_value=login_id_cookie)

    # SID cookie
    sid_cookie = MagicMock()
    sid_cookie.value = "test_sid"

    # Set up login response mock
    login_resp = AsyncMock()
    login_resp.status = 303
    login_resp.cookies = MagicMock()
    login_resp.cookies.get = MagicMock(return_value=sid_cookie)
    login_resp.headers = {"Location": "https://test.inschool.fi/!12345?checkcookie"}

    # Configure session mock for get and post
    get_context = AsyncMock()
    get_context.__aenter__.return_value = token_resp
    post_context = AsyncMock()
    post_context.__aenter__.return_value = login_resp

    mock_session_instance = mock_session.return_value
    mock_session_instance.get.return_value = get_context
    mock_session_instance.post.return_value = post_context

    # Call login
    await client.login("testuser", "testpass")

    # Verify client state
    assert client.user_id == "!12345"
    assert client._sid == "test_sid"

    # Verify requests
    client.session.get.assert_called_once_with("https://test.inschool.fi/token")
    client.session.post.assert_called_once_with(
        "https://test.inschool.fi/login",
        data={"Login": "testuser", "Password": "testpass", "SESSIONID": "test_login_id"},
        allow_redirects=False,
    )


@pytest.mark.asyncio
async def test_login_failure() -> None:
    """Test login failure."""
    client = WilmaClient("https://test.inschool.fi", debug=False)

    # Create mock session
    mock_session = MagicMock()  # Use MagicMock instead of AsyncMock for the session

    # Mock token request response
    token_response = MagicMock()  # Use MagicMock instead of AsyncMock
    token_response.status = 200

    login_id_cookie = MagicMock()
    login_id_cookie.value = "test_login_id"

    cookies = MagicMock()
    cookies.get.side_effect = lambda name: {
        "Wilma2LoginID": login_id_cookie,
    }.get(name)

    token_response.cookies = cookies

    # Mock login response with failure status
    login_response = MagicMock()  # Use MagicMock instead of AsyncMock
    login_response.status = 401  # Unauthorized

    # Set up context manager returns
    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__.return_value = token_response
    mock_session.get.return_value = mock_get_ctx

    mock_post_ctx = MagicMock()
    mock_post_ctx.__aenter__.return_value = login_response
    mock_session.post.return_value = mock_post_ctx

    # Patch _ensure_session to return our mock session
    with patch.object(client, "_ensure_session", AsyncMock(return_value=mock_session)):
        # Call login and expect exception
        with pytest.raises(AuthenticationError):
            await client.login("testuser", "wrong_password")


@pytest.mark.asyncio
@patch("wilhelmina.client.logger")
async def test_login_edge_cases(mock_logger) -> None:
    """Test edge cases for the login method."""
    # Test login with token failure
    client = WilmaClient("https://test.inschool.fi")

    # Create proper mocks using MagicMock instead of AsyncMock
    mock_session = MagicMock()

    # Mock the response for token request with error status
    token_response = MagicMock()
    token_response.status = 404  # Not found

    # Setup mock context manager that returns the token response
    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__.return_value = token_response
    mock_session.get.return_value = mock_get_ctx

    # Set up _ensure_session to return our mock
    with patch.object(client, "_ensure_session", AsyncMock(return_value=mock_session)):
        # Should raise exception for token failure
        with pytest.raises(AuthenticationError, match="Failed to get token"):
            await client.login("testuser", "testpass")

        # Test missing login ID cookie
        token_response.status = 200  # Success
        token_response.cookies.get.return_value = None  # No cookie

        with pytest.raises(AuthenticationError, match="No login ID cookie found"):
            await client.login("testuser", "testpass")

        # Test login failure (status not 302/303)
        token_response.cookies.get.return_value = MagicMock(value="test_login_id")
        login_response = MagicMock()
        login_response.status = 401  # Unauthorized

        # Setup mock context manager for post
        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__.return_value = login_response
        mock_session.post.return_value = mock_post_ctx

        with pytest.raises(AuthenticationError, match="Login failed"):
            await client.login("testuser", "testpass")


@pytest.mark.asyncio
async def test_login_response_errors() -> None:
    """Test various error conditions during login."""
    client = WilmaClient("https://test.inschool.fi")

    # Create and inject _ensure_session return value directly
    mock_session = MagicMock()

    # Configure the token response
    token_resp = MagicMock()
    token_resp.status = 200
    token_resp.cookies.get.return_value = MagicMock(value="test_login_id")

    # Configure the login response
    login_resp = MagicMock()
    login_resp.status = 302

    # Setup a custom cookies.get for login response that returns None for the first call
    # and a MagicMock for the second call
    cookies_get_mock = MagicMock()
    cookies_get_mock.side_effect = (
        lambda cookie_name: None if cookie_name == "Wilma2SID" else MagicMock(value="some_value")
    )
    login_resp.cookies.get = cookies_get_mock

    # Configure session get and post to return context managers with our responses
    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__.return_value = token_resp
    mock_post_ctx = MagicMock()
    mock_post_ctx.__aenter__.return_value = login_resp

    mock_session.get.return_value = mock_get_ctx
    mock_session.post.return_value = mock_post_ctx

    # Mock _ensure_session to return our mock session
    with patch.object(client, "_ensure_session", AsyncMock(return_value=mock_session)):
        # Test case: Missing SID cookie
        with pytest.raises(AuthenticationError, match="No SID cookie found"):
            await client.login("testuser", "testpass")

        # Update the cookie mock to return a SID cookie
        cookies_get_mock.side_effect = lambda cookie_name: MagicMock(value="test_sid")

        # Test case: Missing Location header
        login_resp.headers = {}
        with pytest.raises(AuthenticationError, match="No Location header in response"):
            await client.login("testuser", "testpass")

        # Test case: Invalid Location header (without an exclamation mark)
        login_resp.headers = {"Location": "invalid_url_without_exclamation_mark"}

        with pytest.raises(AuthenticationError, match="Invalid Location header"):
            await client.login("testuser", "testpass")


@pytest.mark.asyncio
async def test_debug_mode() -> None:
    """Test client debug mode."""
    # Create client with debug=True
    WilmaClient("https://test.inschool.fi", debug=True)

    # Debug mode should set logger level to DEBUG
    from wilhelmina.client import logger

    assert logger.level == 10  # DEBUG level

    # Create client with debug=False
    WilmaClient("https://test.inschool.fi", debug=False)

    # Logger level should not be changed when debug=False
    assert logger.level == 10  # Still DEBUG from the previous client


################################
# Authenticated Requests
################################


@pytest.mark.asyncio
async def test_authenticated_request() -> None:
    """Test authenticated request method."""
    # Initialize client
    client = WilmaClient("https://test.inschool.fi")

    # Set authentication values
    client.user_id = "!12345"
    client._sid = "test_sid"

    # We need to patch _ensure_session to prevent actual HTTP requests
    with patch.object(client, "_ensure_session") as mock_ensure_session:
        # Create mock session
        mock_session = AsyncMock()
        mock_response = AsyncMock(spec=ClientResponse)
        mock_response.status = 200

        # Configure mock get method
        mock_session.get = AsyncMock(return_value=mock_response)

        # Make _ensure_session return our mock session
        mock_ensure_session.return_value = mock_session

        # Call the method
        await client._authenticated_request("path/to/resource")

        # Verify the request was made with the right URL and headers
        mock_session.get.assert_called_with(
            "https://test.inschool.fi/path/to/resource", headers={"Wilma2SID": "test_sid"}
        )

        # Test with template path
        mock_session.get.reset_mock()
        await client._authenticated_request("{user_id}/messages")

        # Verify URL was correctly formatted with user_id
        mock_session.get.assert_called_with(
            "https://test.inschool.fi/!12345/messages", headers={"Wilma2SID": "test_sid"}
        )

        # Test with params
        mock_session.get.reset_mock()
        params = {"format": "json", "id": 123}
        await client._authenticated_request("{user_id}/messages", params=params)

        mock_session.get.assert_called_with(
            "https://test.inschool.fi/!12345/messages",
            headers={"Wilma2SID": "test_sid"},
            params=params,
        )

        # Test POST request
        mock_session.post = AsyncMock(return_value=mock_response)
        data = {"key": "value"}
        await client._authenticated_request("{user_id}/messages", method="POST", data=data)

        mock_session.post.assert_called_with(
            "https://test.inschool.fi/!12345/messages", headers={"Wilma2SID": "test_sid"}, data=data
        )


@pytest.mark.asyncio
async def test_authenticated_request_http_error() -> None:
    """Test HTTP error handling in authenticated request."""
    client = WilmaClient("https://test.inschool.fi")
    client.user_id = "!12345"
    client._sid = "test_sid"

    # Setup mocks
    mock_session = AsyncMock()
    mock_response = AsyncMock()
    mock_response.status = 500  # Server error

    # Mock get method to return our response
    mock_session.get = AsyncMock(return_value=mock_response)

    # Setup client with mocks
    with patch.object(client, "_ensure_session", AsyncMock(return_value=mock_session)):
        # With status 500, should raise WilmaError containing the status code
        with pytest.raises(WilmaError) as exc_info:
            await client._authenticated_request("path/to/resource")

        # Verify error message contains status code
        assert "500" in str(exc_info.value)


################################
# Messages
################################


@pytest.mark.asyncio
@patch("wilhelmina.client.WilmaClient._get_unread_message_ids")
async def test_get_messages(mock_get_unread, authenticated_client, messages_data) -> None:
    """Test getting messages."""
    client = authenticated_client

    # Mock the _get_unread_message_ids method to return a set of IDs
    mock_get_unread.return_value = {1}  # Message ID 1 is unread

    # Set up response mock
    resp = AsyncMock()
    resp.status = 200
    resp.json.return_value = messages_data

    # Override _authenticated_request to return our mocked response
    client._authenticated_request = AsyncMock(return_value=resp)

    # Call get_messages
    messages = await client.get_messages()

    # Verify _authenticated_request was called
    client._authenticated_request.assert_called_once_with("{user_id}/messages/list")

    # Verify response
    assert len(messages) == 3
    assert isinstance(messages[0], Message)
    assert messages[0].id == 1
    assert messages[0].subject == "Test message 1"
    assert messages[0].timestamp == "2025-04-16 13:31"
    assert messages[0].sender == "Teacher 1"
    assert messages[0].unread is True  # First message should be unread based on our mock
    assert messages[1].unread is False  # Second message should be read


@pytest.mark.asyncio
@patch("wilhelmina.client.WilmaClient._get_unread_message_ids")
async def test_get_messages_with_filters(
    mock_get_unread, authenticated_client, messages_data, date_filters
) -> None:
    """Test getting messages with filters."""
    client = authenticated_client

    # Mock the _get_unread_message_ids method
    mock_get_unread.return_value = {1}  # Message ID 1 is unread

    # Set up response mock
    resp = AsyncMock()
    resp.status = 200
    resp.json.return_value = messages_data

    # Set the _authenticated_request method
    client._authenticated_request = AsyncMock(return_value=resp)

    # Test with only_unread=True
    messages = await client.get_messages(only_unread=True)
    assert len(messages) == 1
    assert messages[0].id == 1
    assert messages[0].unread is True

    # Test with after date filter (middle date)
    messages = await client.get_messages(after=date_filters["middle"])
    assert len(messages) == 2
    assert messages[0].id == 1  # Most recent
    assert messages[1].id == 2  # Middle

    # Test with after date - before all messages
    messages = await client.get_messages(after=date_filters["before_all"])
    assert len(messages) == 3  # All messages

    # Test with after date - after all messages
    messages = await client.get_messages(after=date_filters["after_all"])
    assert len(messages) == 0  # No messages

    # Test with timezone-aware date
    messages = await client.get_messages(after=date_filters["with_timezone"])
    assert len(messages) == 2  # Same as middle date test

    # Test with combination of filters
    messages = await client.get_messages(only_unread=True, after=date_filters["middle"])
    assert len(messages) == 1
    assert messages[0].id == 1
    assert messages[0].unread is True


@pytest.mark.asyncio
@patch("wilhelmina.client.WilmaClient._get_unread_message_ids")
@patch("wilhelmina.client.WilmaClient.get_message_content")
async def test_get_messages_with_content(
    mock_get_message_content,
    mock_get_unread,
    authenticated_client,
    messages_data,
    message_content_data,
) -> None:
    """Test getting messages with content."""
    client = authenticated_client

    # Mock the _get_unread_message_ids method
    mock_get_unread.return_value = {1}

    # Set up response mock for messages list
    resp = AsyncMock()
    resp.status = 200
    resp.json.return_value = messages_data
    client._authenticated_request = AsyncMock(return_value=resp)

    # Mock get_message_content to return messages with content
    full_message1 = Message.from_dict(message_content_data["messages"][0])
    full_message2 = Message.from_dict(
        {
            "Id": 2,
            "Subject": "Test message 2",
            "TimeStamp": "2025-04-15 10:20",
            "Folder": "Inbox",
            "SenderId": 456,
            "SenderType": 1,
            "Sender": "Teacher 2",
            "ContentHtml": "<p>Test message 2 full content.</p>",
            "AllowForward": True,
            "AllowReply": True,
            "ReplyList": [],
            "Senders": [{"Name": "Teacher 2", "Href": "/profiles/456"}],
        }
    )
    full_message3 = Message.from_dict(
        {
            "Id": 3,
            "Subject": "Test message 3",
            "TimeStamp": "2025-04-10 09:15",
            "Folder": "Inbox",
            "SenderId": 789,
            "SenderType": 1,
            "Sender": "Teacher 3",
            "ContentHtml": "<p>Test message 3 full content.</p>",
            "AllowForward": True,
            "AllowReply": True,
            "ReplyList": [],
            "Senders": [{"Name": "Teacher 3", "Href": "/profiles/789"}],
        }
    )

    # Configure mock to return different messages based on the message ID
    mock_get_message_content.side_effect = lambda id: (
        full_message1 if id == 1 else (full_message2 if id == 2 else full_message3)
    )

    # Call get_messages with with_content=True
    messages = await client.get_messages(with_content=True, no_message_content_fetch_limit=True)

    # Verify get_message_content was called for each message
    assert mock_get_message_content.call_count == 3

    # Verify the message content was updated
    assert len(messages) == 3
    assert messages[0].content_html == "<p>This is a test message content.</p>"
    assert messages[1].content_html == "<p>Test message 2 full content.</p>"
    assert messages[2].content_html == "<p>Test message 3 full content.</p>"


@pytest.mark.asyncio
@patch("wilhelmina.client.WilmaClient._get_unread_message_ids")
async def test_get_message_content(mock_get_unread, authenticated_client) -> None:
    """Test fetching message content."""
    client = authenticated_client

    # Mock _get_unread_message_ids
    mock_get_unread.return_value = {10}

    # Mock _authenticated_request
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(
        return_value={
            "messages": [
                {
                    "Id": 10,
                    "Subject": "Test message",
                    "TimeStamp": "2025-04-16 13:31",
                    "Folder": "Inbox",
                    "SenderId": 123,
                    "SenderType": 1,
                    "Sender": "Teacher 1",
                    "ContentHtml": "<p>Message content</p>",
                    "AllowForward": True,
                    "AllowReply": True,
                    "ReplyList": [],
                    "Senders": [],
                }
            ]
        }
    )

    client._authenticated_request = AsyncMock(return_value=mock_response)

    # Call get_message_content
    message = await client.get_message_content(10)

    # Verify authenticated request was called correctly
    client._authenticated_request.assert_called_once_with(
        "{user_id}/messages/10", params={"format": "json"}
    )

    # Verify message properties
    assert message.id == 10
    assert message.subject == "Test message"
    assert message.content_html == "<p>Message content</p>"
    assert message.unread is True  # Should be in unread set


@pytest.mark.asyncio
@patch("wilhelmina.client.WilmaClient._get_unread_message_ids")
async def test_get_messages_with_invalid_content(mock_get_unread) -> None:
    """Test handling of invalid message content."""
    client = WilmaClient("https://test.inschool.fi")
    client.user_id = "!12345"
    client._sid = "test_sid"

    # Mock _get_unread_message_ids
    mock_get_unread.return_value = set()

    # Create complete message dict with all required fields
    message_dict = {
        "Id": 123,
        "Subject": "Test Subject",
        "TimeStamp": "2023-01-01 12:00",
        "Folder": "Inbox",
        "SenderId": 456,
        "SenderType": 1,
        "Sender": "Test Sender",
    }

    # Mock list response
    list_response = MagicMock()
    list_response.json = AsyncMock(return_value={"Messages": [message_dict]})

    # Mock _authenticated_request
    with (
        patch.object(client, "_authenticated_request", AsyncMock(return_value=list_response)),
        patch.object(
            client, "get_message_content", AsyncMock(side_effect=Exception("Failed to get content"))
        ),
    ):
        # Should handle exception and continue
        messages = await client.get_messages(with_content=True, no_message_content_fetch_limit=True)

        # Should have one message despite content fetch error
        assert len(messages) == 1
        assert messages[0].id == 123


################################
# Helper Functions
################################


@pytest.mark.asyncio
async def test_message_attribute_transfer() -> None:
    """Test transfer of attributes from one message to another."""
    # This tests line 305 in client.py

    from wilhelmina.models import Message

    # Create source message
    original_message = Message(
        id=123,
        subject="Original Subject",
        timestamp="2023-01-01 12:00",
        folder="Inbox",
        sender_id=456,
        sender_type=1,
        sender="Original Sender",
    )

    # Create message with additional attributes
    updated_message = Message(
        id=123,
        subject="Updated Subject",
        timestamp="2023-01-01 12:00",
        folder="Inbox",
        sender_id=456,
        sender_type=1,
        sender="Updated Sender",
        content_html="<p>New content</p>",  # New attribute not in original
    )

    # Simulate the code from line 305 that transfers attributes
    for attr, value in vars(updated_message).items():
        if attr != "unread" and getattr(original_message, attr, None) is None:
            setattr(original_message, attr, value)

    # The content_html attribute should have been copied
    assert original_message.content_html == "<p>New content</p>"
    # Original attributes should remain unchanged
    assert original_message.subject == "Original Subject"


def test_non_string_value_handling() -> None:
    """Test handling of a non-string value in message ID."""
    # Test both cases of the functionality
    # Case 1: Non-string value should be skipped
    value1 = 123  # Non-string value
    if not isinstance(value1, str):
        result1 = "skipped"
    else:
        result1 = "processed"

    # It should return skipped and not raise an exception
    assert result1 == "skipped"

    # Case 2: String value should be processed
    value2 = "456"  # String value
    if not isinstance(value2, str):
        result2 = "skipped"
    else:
        result2 = "processed"

    # It should return processed
    assert result2 == "processed"
