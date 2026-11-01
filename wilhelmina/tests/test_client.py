"""Tests for WilmaClient."""

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from wilhelmina.client import AuthenticationError, WilmaClient, WilmaError
from wilhelmina.models import Message, MessageFolder, Reply

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
@patch("wilhelmina.client.aiohttp.ClientSession")
async def test_login_checkcookie_style_checkcookie_redirect(mock_session) -> None:
    """Test checkcookie style login with checkcookie redirect (no user ID in initial redirect)."""
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

    # Set up login response mock - checkcookie style (no user ID, just checkcookie)
    login_resp = AsyncMock()
    login_resp.status = 302
    login_resp.cookies = MagicMock()
    login_resp.cookies.get = MagicMock(return_value=sid_cookie)
    login_resp.headers = {"Location": "https://test.inschool.fi/?checkcookie"}

    # Set up checkcookie redirect response
    checkcookie_resp = AsyncMock()
    checkcookie_resp.status = 302
    checkcookie_resp.headers = {"Location": "https://test.inschool.fi/"}

    # Set up home page response with user ID in content
    home_resp = AsyncMock()
    home_resp.status = 200
    home_resp.text = AsyncMock(
        return_value="""
        <html>
            <body>
                <script>
                    var userUrl = "/!9876543/index";
                    window.location = userUrl;
                </script>
            </body>
        </html>
    """
    )

    # Configure session mock
    mock_session_instance = mock_session.return_value

    # Set up context managers for different requests
    token_context = AsyncMock()
    token_context.__aenter__.return_value = token_resp

    login_context = AsyncMock()
    login_context.__aenter__.return_value = login_resp

    checkcookie_context = AsyncMock()
    checkcookie_context.__aenter__.return_value = checkcookie_resp

    home_context = AsyncMock()
    home_context.__aenter__.return_value = home_resp

    # Configure get and post methods to return appropriate context managers
    def get_side_effect(url, **kwargs):
        if "/token" in url:
            return token_context
        elif "checkcookie" in url:
            return checkcookie_context
        else:  # home page
            return home_context

    mock_session_instance.get.side_effect = get_side_effect
    mock_session_instance.post.return_value = login_context

    # Call login
    await client.login("testuser", "testpass")

    # Verify client state - should have extracted user ID from home page
    assert client.user_id == "!9876543"
    assert client._sid == "test_sid"

    # Verify the sequence of requests
    assert mock_session_instance.get.call_count == 3  # token, checkcookie, home page
    assert mock_session_instance.post.call_count == 1  # login


@pytest.mark.asyncio
@patch("wilhelmina.client.aiohttp.ClientSession")
async def test_login_checkcookie_style_no_redirect_from_checkcookie(mock_session) -> None:
    """Test checkcookie style login when checkcookie doesn't redirect (status 200)."""
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

    # Set up login response mock - checkcookie style
    login_resp = AsyncMock()
    login_resp.status = 302
    login_resp.cookies = MagicMock()
    login_resp.cookies.get = MagicMock(return_value=sid_cookie)
    login_resp.headers = {"Location": "https://test.inschool.fi/?checkcookie"}

    # Set up checkcookie response that doesn't redirect (status 200)
    checkcookie_resp = AsyncMock()
    checkcookie_resp.status = 200

    # Set up home page response with user ID
    home_resp = AsyncMock()
    home_resp.status = 200
    home_resp.text = AsyncMock(
        return_value="""
        <html>
            <body>
                <div id="user-info" data-user-id="!9876543">Welcome</div>
            </body>
        </html>
    """
    )

    # Configure session mock
    mock_session_instance = mock_session.return_value

    # Set up context managers
    token_context = AsyncMock()
    token_context.__aenter__.return_value = token_resp

    login_context = AsyncMock()
    login_context.__aenter__.return_value = login_resp

    checkcookie_context = AsyncMock()
    checkcookie_context.__aenter__.return_value = checkcookie_resp

    home_context = AsyncMock()
    home_context.__aenter__.return_value = home_resp

    def get_side_effect(url, **kwargs):
        if "/token" in url:
            return token_context
        elif "checkcookie" in url and kwargs.get("allow_redirects") is False:
            return checkcookie_context
        else:  # home page (when checkcookie doesn't redirect)
            return home_context

    mock_session_instance.get.side_effect = get_side_effect
    mock_session_instance.post.return_value = login_context

    # Call login
    await client.login("testuser", "testpass")

    # Verify client state
    assert client.user_id == "!9876543"
    assert client._sid == "test_sid"


@pytest.mark.asyncio
@patch("wilhelmina.client.aiohttp.ClientSession")
async def test_login_checkcookie_style_user_id_extraction_patterns(mock_session) -> None:
    """Test different patterns for extracting user ID from checkcookie home page."""
    client = WilmaClient("https://test.inschool.fi", debug=False)

    # Setup basic mocks
    login_id_cookie = MagicMock()
    login_id_cookie.value = "test_login_id"

    token_resp = AsyncMock()
    token_resp.status = 200
    token_resp.cookies = MagicMock()
    token_resp.cookies.get = MagicMock(return_value=login_id_cookie)

    sid_cookie = MagicMock()
    sid_cookie.value = "test_sid"

    login_resp = AsyncMock()
    login_resp.status = 302
    login_resp.cookies = MagicMock()
    login_resp.cookies.get = MagicMock(return_value=sid_cookie)
    login_resp.headers = {"Location": "https://test.inschool.fi/?checkcookie"}

    checkcookie_resp = AsyncMock()
    checkcookie_resp.status = 302
    checkcookie_resp.headers = {"Location": "https://test.inschool.fi/"}

    mock_session_instance = mock_session.return_value

    # Test pattern 1: URL in quotes
    home_resp1 = AsyncMock()
    home_resp1.status = 200
    home_resp1.text = AsyncMock(return_value='<script>var url = "/!9876543/messages";</script>')

    # Test pattern 2: userId variable
    home_resp2 = AsyncMock()
    home_resp2.status = 200
    home_resp2.text = AsyncMock(return_value='<script>userId = "!9876544";</script>')

    test_cases = [
        (home_resp1, "!9876543"),
        (home_resp2, "!9876544"),
    ]

    for home_resp, expected_user_id in test_cases:
        # Reset client state
        client.user_id = None
        client._sid = None

        # Set up context managers
        token_context = AsyncMock()
        token_context.__aenter__.return_value = token_resp

        login_context = AsyncMock()
        login_context.__aenter__.return_value = login_resp

        checkcookie_context = AsyncMock()
        checkcookie_context.__aenter__.return_value = checkcookie_resp

        home_context = AsyncMock()
        home_context.__aenter__.return_value = home_resp

        def get_side_effect(
            url,
            token_ctx=token_context,
            checkcookie_ctx=checkcookie_context,
            home_ctx=home_context,
            **kwargs,
        ):
            if "/token" in url:
                return token_ctx
            elif "checkcookie" in url:
                return checkcookie_ctx
            else:
                return home_ctx

        mock_session_instance.get.side_effect = get_side_effect
        mock_session_instance.post.return_value = login_context

        # Call login
        await client.login("testuser", "testpass")

        # Verify the expected user ID was extracted
        assert client.user_id == expected_user_id


@pytest.mark.asyncio
@patch("wilhelmina.client.aiohttp.ClientSession")
async def test_login_checkcookie_style_extraction_failure(mock_session) -> None:
    """Test checkcookie style login when user ID cannot be extracted from home page."""
    client = WilmaClient("https://test.inschool.fi", debug=False)

    # Setup mocks
    login_id_cookie = MagicMock()
    login_id_cookie.value = "test_login_id"

    token_resp = AsyncMock()
    token_resp.status = 200
    token_resp.cookies = MagicMock()
    token_resp.cookies.get = MagicMock(return_value=login_id_cookie)

    sid_cookie = MagicMock()
    sid_cookie.value = "test_sid"

    login_resp = AsyncMock()
    login_resp.status = 302
    login_resp.cookies = MagicMock()
    login_resp.cookies.get = MagicMock(return_value=sid_cookie)
    login_resp.headers = {"Location": "https://test.inschool.fi/?checkcookie"}

    checkcookie_resp = AsyncMock()
    checkcookie_resp.status = 302
    checkcookie_resp.headers = {"Location": "https://test.inschool.fi/"}

    # Home page without user ID pattern
    home_resp = AsyncMock()
    home_resp.status = 200
    home_resp.text = AsyncMock(return_value="<html><body><h1>Welcome to Wilma</h1></body></html>")

    mock_session_instance = mock_session.return_value

    # Set up context managers
    token_context = AsyncMock()
    token_context.__aenter__.return_value = token_resp

    login_context = AsyncMock()
    login_context.__aenter__.return_value = login_resp

    checkcookie_context = AsyncMock()
    checkcookie_context.__aenter__.return_value = checkcookie_resp

    home_context = AsyncMock()
    home_context.__aenter__.return_value = home_resp

    def get_side_effect(url, **kwargs):
        if "/token" in url:
            return token_context
        elif "checkcookie" in url:
            return checkcookie_context
        else:
            return home_context

    mock_session_instance.get.side_effect = get_side_effect
    mock_session_instance.post.return_value = login_context

    # Should raise AuthenticationError when user ID cannot be extracted
    with pytest.raises(AuthenticationError, match="Could not extract user ID from home page"):
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
    cookies_get_mock.side_effect = lambda cookie_name: (
        None if cookie_name == "Wilma2SID" else MagicMock(value="some_value")
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
# Requests
################################


def _response_cm(
    status: int = 200,
    location: str | None = None,
    json_data: object = None,
    json_exc: Exception | None = None,
    text: str = "",
) -> MagicMock:
    """Build an async context manager mimicking ``session.get(...)``."""
    resp = MagicMock()
    resp.status = status
    resp.headers = {"Location": location} if location else {}
    resp.json = AsyncMock(return_value=json_data, side_effect=json_exc)
    resp.text = AsyncMock(return_value=text)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _client_with_session(*responses: MagicMock) -> tuple[WilmaClient, MagicMock]:
    client = WilmaClient("https://test.inschool.fi")
    client.user_id = "!12345"
    client._sid = "test_sid"
    session = MagicMock()
    session.closed = False
    session.get = MagicMock(side_effect=list(responses))
    client.session = session
    return client, session


@pytest.mark.asyncio
async def test_get_json_builds_url_and_headers() -> None:
    client, session = _client_with_session(_response_cm(json_data={"ok": True}))

    data = await client._get_json("messages/1", params={"format": "json"})

    assert data == {"ok": True}
    session.get.assert_called_once_with(
        "https://test.inschool.fi/!12345/messages/1",
        headers={"Wilma2SID": "test_sid"},
        params={"format": "json"},
        allow_redirects=False,
    )


@pytest.mark.asyncio
async def test_get_json_site_root() -> None:
    client, session = _client_with_session(_response_cm(json_data={"payload": []}))

    await client._get_json("api/v1/accounts/me/roles", user_scoped=False)

    assert session.get.call_args.args[0] == "https://test.inschool.fi/api/v1/accounts/me/roles"


@pytest.mark.asyncio
async def test_get_json_for_other_user() -> None:
    client, session = _client_with_session(_response_cm(json_data={}))

    await client._get_json("messages/list", user_id="!67890")

    assert session.get.call_args.args[0] == "https://test.inschool.fi/!67890/messages/list"


@pytest.mark.asyncio
async def test_relogin_keeps_requested_user() -> None:
    client, session = _client_with_session(
        _response_cm(status=302, location="/login?invalidsession"), _response_cm(json_data={})
    )
    client.login = AsyncMock()

    await client._get_json("messages/list", user_id="!67890")

    assert session.get.call_args.args[0] == "https://test.inschool.fi/!67890/messages/list"


@pytest.mark.asyncio
async def test_data_methods_pass_user_id(authenticated_client, message_content_data) -> None:
    client = authenticated_client
    client._get_json = AsyncMock(return_value=message_content_data)
    client._get_text = AsyncMock(return_value="<html></html>")

    await client.get_messages(user_id="!67890")
    await client.get_message_content(1, user_id="!67890")
    await client.get_attendance(user_id="!67890")

    for call in [*client._get_json.await_args_list, *client._get_text.await_args_list]:
        assert call.kwargs["user_id"] == "!67890"


@pytest.mark.asyncio
async def test_get_text() -> None:
    client, _ = _client_with_session(_response_cm(text="<html></html>"))

    assert await client._get_text("attendance/view", params={"range": "0"}) == "<html></html>"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [aiohttp.ClientConnectionError("down"), TimeoutError()])
async def test_get_network_error_is_wilma_error(error: Exception) -> None:
    client, session = _client_with_session()
    session.get = MagicMock(side_effect=error)

    with pytest.raises(WilmaError, match="Request to .* failed"):
        await client._get_json("messages/list")


@pytest.mark.asyncio
async def test_get_unexpected_redirect() -> None:
    client, _ = _client_with_session(
        _response_cm(status=302, location="https://test.inschool.fi/!12345/elsewhere")
    )
    client.login = AsyncMock()

    with pytest.raises(WilmaError, match="Unexpected redirect"):
        await client._get_json("messages/list")
    client.login.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_json_http_error() -> None:
    client, _ = _client_with_session(_response_cm(status=500))

    with pytest.raises(WilmaError, match="500"):
        await client._get_json("messages/list")


@pytest.mark.asyncio
async def test_get_json_non_json_response() -> None:
    client, _ = _client_with_session(_response_cm(json_exc=ValueError("not json")))

    with pytest.raises(WilmaError, match="Expected JSON"):
        await client._get_json("messages/list")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expired",
    [
        {"status": 302, "location": "/login?returnpath=!12345%2Fmessages%2Flist"},
        {
            "status": 302,
            "location": "https://test.inschool.fi/login?invalidsession&returnpath=!12345%2F",
        },
        {"status": 302, "location": "https://test.inschool.fi/?sessionexpired"},
        {"status": 403},
        {"status": 401},
    ],
)
async def test_get_json_relogins_once_on_expired_session(expired: dict) -> None:
    client, session = _client_with_session(
        _response_cm(**expired), _response_cm(json_data={"Messages": []})
    )
    client.login = AsyncMock()

    data = await client._get_json("messages/list")

    assert data == {"Messages": []}
    client.login.assert_awaited_once()
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_get_json_gives_up_after_one_relogin() -> None:
    client, session = _client_with_session(_response_cm(status=401), _response_cm(status=401))
    client.login = AsyncMock()

    with pytest.raises(AuthenticationError, match="re-login did not help"):
        await client._get_json("messages/list")

    client.login.assert_awaited_once()
    assert session.get.call_count == 2


@pytest.mark.asyncio
async def test_get_json_access_denied_after_relogin() -> None:
    denied = {"error": {"id": "common-403", "description": "No access to this feature."}}
    client, session = _client_with_session(
        _response_cm(status=403, json_data=denied), _response_cm(status=403, json_data=denied)
    )
    client.login = AsyncMock()

    with pytest.raises(WilmaError, match="Access denied .*No access to this feature") as exc:
        await client._get_json("attendance/index_json")

    assert not isinstance(exc.value, AuthenticationError)
    client.login.assert_awaited_once()


def test_client_is_read_only() -> None:
    """Login is the only non-GET request the client is allowed to make."""
    import inspect

    import wilhelmina.client as client_module

    source = inspect.getsource(client_module)
    for verb in ("put", "patch", "delete", "request", "options"):
        assert f"session.{verb}(" not in source
    assert source.count("session.post(") == 1
    assert "session.post(" in inspect.getsource(WilmaClient.login)


################################
# Messages
################################


@pytest.mark.asyncio
async def test_get_messages(authenticated_client, messages_data) -> None:
    client = authenticated_client
    client._get_json = AsyncMock(return_value=messages_data)

    messages = await client.get_messages()

    client._get_json.assert_awaited_once_with("messages/list", user_id=None)
    assert len(messages) == 3
    assert isinstance(messages[0], Message)
    assert messages[0].id == 1
    assert messages[0].subject == "Test message 1"
    assert messages[0].timestamp == "2025-04-16 13:31"
    assert messages[0].sender == "Teacher 1"
    assert messages[0].status == 1
    assert messages[0].unread is True
    assert messages[1].unread is False
    assert messages[2].unread is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("folder", "path"),
    [
        (MessageFolder.INBOX, "messages/list"),
        (MessageFolder.ARCHIVE, "messages/list/archive"),
        (MessageFolder.OUTBOX, "messages/list/outbox"),
        (MessageFolder.DRAFTS, "messages/list/drafts"),
        (MessageFolder.APPOINTMENTS, "messages/list/appointments"),
    ],
)
async def test_get_messages_folder_paths(authenticated_client, folder, path) -> None:
    client = authenticated_client
    client._get_json = AsyncMock(return_value={"Messages": []})

    assert await client.get_messages(folder=folder) == []
    client._get_json.assert_awaited_once_with(path, user_id=None)


@pytest.mark.asyncio
async def test_get_messages_with_filters(authenticated_client, messages_data, date_filters) -> None:
    client = authenticated_client
    client._get_json = AsyncMock(return_value=messages_data)

    messages = await client.get_messages(only_unread=True)
    assert [m.id for m in messages] == [1]

    messages = await client.get_messages(after=date_filters["middle"])
    assert [m.id for m in messages] == [1, 2]

    messages = await client.get_messages(after=date_filters["before_all"])
    assert len(messages) == 3

    messages = await client.get_messages(after=date_filters["after_all"])
    assert messages == []

    messages = await client.get_messages(after=date_filters["with_timezone"])
    assert [m.id for m in messages] == [1, 2]

    # 2025-04-15 07:00 UTC is 10:00 in Helsinki, before message 2 (10:20)
    utc = datetime.datetime(2025, 4, 15, 7, 0, tzinfo=datetime.timezone.utc)
    assert [m.id for m in await client.get_messages(after=utc)] == [1, 2]
    # 2025-04-15 07:30 UTC is 10:30 in Helsinki, after message 2
    utc = datetime.datetime(2025, 4, 15, 7, 30, tzinfo=datetime.timezone.utc)
    assert [m.id for m in await client.get_messages(after=utc)] == [1]

    messages = await client.get_messages(only_unread=True, after=date_filters["middle"])
    assert [m.id for m in messages] == [1]


@pytest.mark.asyncio
async def test_get_messages_with_content(
    authenticated_client, messages_data, message_content_data
) -> None:
    client = authenticated_client
    client._get_json = AsyncMock(return_value=messages_data)

    def full(message_id: int, user_id: str | None = None) -> Message:
        data = dict(message_content_data["messages"][0])
        data["Id"] = message_id
        data["ContentHtml"] = f"<p>Content {message_id}</p>"
        return Message.from_dict(data)

    client.get_message_content = AsyncMock(side_effect=full)

    messages = await client.get_messages(with_content=True)

    assert client.get_message_content.await_count == 3
    assert [m.content_html for m in messages] == [
        "<p>Content 1</p>",
        "<p>Content 2</p>",
        "<p>Content 3</p>",
    ]
    assert messages[0].reply_list[0].sender == "Teacher 1"
    assert messages[0].recipients == ["Guardian A"]
    assert messages[0].recipient_count == 1
    # unread reflects the listing, taken before the content fetch marked it read
    assert messages[0].unread is True


@pytest.mark.asyncio
async def test_get_messages_with_content_failure_keeps_message(
    authenticated_client, messages_data
) -> None:
    client = authenticated_client
    client._get_json = AsyncMock(return_value=messages_data)
    client.get_message_content = AsyncMock(side_effect=WilmaError("boom"))

    messages = await client.get_messages(with_content=True)

    assert len(messages) == 3
    assert messages[0].content_html is None


@pytest.mark.asyncio
async def test_get_message_content(authenticated_client, message_content_data) -> None:
    client = authenticated_client
    client._get_json = AsyncMock(return_value=message_content_data)

    message = await client.get_message_content(1)

    client._get_json.assert_awaited_once_with("messages/1", params={"format": "json"}, user_id=None)
    assert message.id == 1
    assert message.content_html == "<p>This is a test message content.</p>"
    assert message.content_markdown == "This is a test message content."
    assert len(message.reply_list) == 1
    reply = message.reply_list[0]
    assert isinstance(reply, Reply)
    assert reply.id == "1s15:16"
    assert reply.content_markdown == "Thanks!"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"messages": []}, {"messages": None}])
async def test_get_message_content_unexpected_response(authenticated_client, payload) -> None:
    client = authenticated_client
    client._get_json = AsyncMock(return_value=payload)

    with pytest.raises(WilmaError, match="Unexpected message response"):
        await client.get_message_content(1)
