"""Tests for models."""

from datetime import datetime

import pytest

from wilhelmina.models import Message, MessagesList, Sender


def test_sender_model() -> None:
    """Test Sender model."""
    data = {"name": "Teacher 1", "href": "/profiles/123"}
    sender = Sender(**data)

    assert sender.name == "Teacher 1"
    assert sender.href == "/profiles/123"


def test_message_model() -> None:
    """Test Message model."""
    data = {
        "id": 1,
        "subject": "Test message",
        "timestamp": "2025-04-16 13:31",
        "folder": "Inbox",
        "sender_id": 123,
        "sender_type": 1,
        "sender": "Teacher 1",
        "content_html": "<p>This is a test message.</p>",
        "allow_forward": True,
        "allow_reply": True,
        "reply_list": [],
        "senders": [Sender(name="Teacher 1", href="/profiles/123")],
        "unread": False,
    }

    message = Message(**data)

    assert message.id == 1
    assert message.subject == "Test message"
    assert message.timestamp == "2025-04-16 13:31"
    assert message.folder == "Inbox"
    assert message.sender_id == 123
    assert message.sender_type == 1
    assert message.sender == "Teacher 1"
    assert message.content_html == "<p>This is a test message.</p>"
    assert message.content_markdown == "This is a test message."
    assert message.allow_forward is True
    assert message.allow_reply is True
    assert message.reply_list == []
    assert len(message.senders) == 1
    assert message.senders[0].name == "Teacher 1"
    assert message.senders[0].href == "/profiles/123"


def test_content_markdown_error() -> None:
    """Test that accessing content_markdown raises error when content_html is None."""
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


def test_message_format_timestamp() -> None:
    """Test the format_timestamp method."""
    message = Message(
        id=1,
        subject="Test message",
        timestamp="2025-04-16 13:31",
        folder="Inbox",
        sender_id=123,
        sender_type=1,
        sender="Teacher 1",
    )

    # Test format_timestamp
    formatted = message.format_timestamp()
    assert isinstance(formatted, datetime)
    assert formatted.year == 2025
    assert formatted.month == 4
    assert formatted.day == 16
    assert formatted.hour == 13
    assert formatted.minute == 31


def test_messages_list_model() -> None:
    """Test MessagesList model."""
    messages = [
        Message(
            id=1,
            subject="Test message 1",
            timestamp="2025-04-16 13:31",
            folder="Inbox",
            sender_id=123,
            sender_type=1,
            sender="Teacher 1",
            content_html="<p>Message 1 content</p>",
            allow_forward=True,
            allow_reply=True,
            reply_list=[],
            senders=[Sender(name="Teacher 1", href="/profiles/123")],
            unread=True,
        ),
        Message(
            id=2,
            subject="Test message 2",
            timestamp="2025-04-15 10:20",
            folder="Inbox",
            sender_id=456,
            sender_type=1,
            sender="Teacher 2",
            content_html="<p>Message 2 content</p>",
            allow_forward=True,
            allow_reply=True,
            reply_list=[],
            senders=[],
            unread=False,
        ),
    ]

    messages_list = MessagesList(messages=messages)

    assert len(messages_list.messages) == 2
    assert messages_list.messages[0].id == 1
    assert messages_list.messages[0].subject == "Test message 1"
    assert messages_list.messages[1].id == 2
    assert messages_list.messages[1].subject == "Test message 2"
