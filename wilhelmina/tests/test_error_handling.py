"""Tests for error handling in WilmaClient."""

from unittest.mock import AsyncMock

import pytest

from wilhelmina.client import AuthenticationError, WilmaClient, WilmaError
from wilhelmina.models import Message


@pytest.mark.asyncio
async def test_not_authenticated() -> None:
    """Test that methods requiring authentication raise errors when not authenticated."""
    client = WilmaClient("https://test.inschool.fi")

    # Methods that require authentication
    with pytest.raises(AuthenticationError, match="Not authenticated"):
        client._check_auth()

    with pytest.raises(AuthenticationError):
        await client.get_messages()

    with pytest.raises(AuthenticationError):
        await client.get_message_content(1)


@pytest.mark.asyncio
async def test_message_content_fetch_limit(authenticated_client) -> None:
    """Test the message content fetch limit."""
    client = authenticated_client

    # With more than 10 messages and no override, should fail
    # Build a response that has > 10 messages
    messages_with_many = {"Messages": []}
    for i in range(15):  # Add 15 messages
        messages_with_many["Messages"].append(
            {
                "Id": i + 1,
                "Subject": f"Test message {i + 1}",
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
        )

    client._get_json = AsyncMock(return_value=messages_with_many)
    client.get_message_content = AsyncMock()

    # Try to fetch content for all messages without override - should fail
    with pytest.raises(WilmaError, match="Not allowed to fetch full message content"):
        await client.get_messages(with_content=True)
    client.get_message_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_content_markdown_error() -> None:
    """Test error when accessing content_markdown with None content_html."""

    # Create message with None content_html
    message = Message(
        id=1,
        subject="Test message",
        timestamp="2025-04-16 13:31",
        folder="Inbox",
        sender_id=123,
        sender_type=1,
        sender="Teacher 1",
        content_html=None,
    )

    # Verify ValueError is raised when trying to access content_markdown
    with pytest.raises(ValueError, match="Message content is not available"):
        _ = message.content_markdown
