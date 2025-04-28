"""Test configuration."""

import datetime
import logging
from typing import Any, Dict, Generator, List
from unittest.mock import AsyncMock

import pytest

from wilhelmina.client import WilmaClient


def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line("markers", "asyncio: mark test as an asyncio test")


@pytest.fixture(autouse=True)
def disable_logging() -> Generator[None, None, None]:
    """Disable logging for tests."""
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


@pytest.fixture
def authenticated_client() -> WilmaClient:
    """Create an authenticated client instance."""
    client = WilmaClient("https://test.inschool.fi", debug=False)
    client.user_id = "!12345"
    client._sid = "test_sid"
    return client


@pytest.fixture
def messages_data() -> Dict[str, List[Dict[str, Any]]]:
    """Mock messages data."""
    return {
        "Messages": [
            {
                "Id": 1,
                "Subject": "Test message 1",
                "TimeStamp": "2025-04-16 13:31",
                "Folder": "Inbox",
                "SenderId": 123,
                "SenderType": 1,
                "Sender": "Teacher 1",
                "ContentHtml": "<p>Message 1 content</p>",
                "AllowForward": True,
                "AllowReply": True,
                "ReplyList": [],
                "Senders": [{"Name": "Teacher 1", "Href": "/profiles/123"}],
            },
            {
                "Id": 2,
                "Subject": "Test message 2",
                "TimeStamp": "2025-04-15 10:20",
                "Folder": "Inbox",
                "SenderId": 456,
                "SenderType": 1,
                "Sender": "Teacher 2",
                "ContentHtml": "<p>Message 2 content</p>",
                "AllowForward": True,
                "AllowReply": True,
                "ReplyList": [],
                "Senders": [{"Name": "Teacher 2", "Href": "/profiles/456"}],
            },
            {
                "Id": 3,
                "Subject": "Test message 3",
                "TimeStamp": "2025-04-10 09:15",  # Oldest
                "Folder": "Inbox",
                "SenderId": 789,
                "SenderType": 1,
                "Sender": "Teacher 3",
                "ContentHtml": "<p>Message 3 content</p>",
                "AllowForward": True,
                "AllowReply": True,
                "ReplyList": [],
                "Senders": [{"Name": "Teacher 3", "Href": "/profiles/789"}],
            },
        ]
    }


@pytest.fixture
def message_content_data() -> Dict[str, Any]:
    """Mock message content data."""
    return {
        "messages": [
            {
                "Id": 1,
                "Subject": "Test message 1",
                "TimeStamp": "2025-04-16 13:31",
                "Folder": "Inbox",
                "SenderId": 123,
                "SenderType": 1,
                "Sender": "Teacher 1",
                "ContentHtml": "<p>This is a test message content.</p>",
                "AllowForward": True,
                "AllowReply": True,
                "ReplyList": [],
                "Senders": [{"Name": "Teacher 1", "Href": "/profiles/123"}],
            }
        ]
    }


@pytest.fixture
def mock_authenticated_request(authenticated_client):
    """Mock the _authenticated_request method."""

    async def _mock_request(url_template, *args, **kwargs):
        resp = AsyncMock()
        resp.status = 200
        return resp

    authenticated_client._authenticated_request = AsyncMock(side_effect=_mock_request)
    return authenticated_client


@pytest.fixture
def date_filters():
    """Return a set of dates for filtering tests."""
    return {
        "before_all": datetime.datetime(2025, 4, 5),
        "middle": datetime.datetime(2025, 4, 12),
        "after_all": datetime.datetime(2025, 4, 25),
        "with_timezone": datetime.datetime(2025, 4, 12, tzinfo=datetime.timezone.utc),
    }
