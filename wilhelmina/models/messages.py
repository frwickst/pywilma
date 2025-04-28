"""Message models for Wilma API."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional

from mashumaro import DataClassDictMixin
from mashumaro.config import BaseConfig

from wilhelmina.utils import html_to_markdown


@dataclass
class Sender(DataClassDictMixin):
    """Sender of a message."""

    name: str
    href: Optional[str] = None

    class Config(BaseConfig):
        aliases = {"name": "Name", "href": "Href"}


@dataclass
class Message(DataClassDictMixin):
    """A message in Wilma."""

    id: int
    subject: str
    timestamp: str
    folder: str
    sender_id: int
    sender_type: int
    sender: str
    content_html: str | None = None
    allow_forward: bool = True
    allow_reply: bool = True
    reply_list: List[Any] = field(default_factory=list)
    senders: List[Sender] = field(default_factory=list)
    unread: bool = False

    class Config(BaseConfig):
        aliases = {
            "id": "Id",
            "subject": "Subject",
            "timestamp": "TimeStamp",
            "folder": "Folder",
            "sender_id": "SenderId",
            "sender_type": "SenderType",
            "sender": "Sender",
            "content_html": "ContentHtml",
            "allow_forward": "AllowForward",
            "allow_reply": "AllowReply",
            "reply_list": "ReplyList",
            "senders": "Senders",
            # unread is not in the API response, we set it manually
        }

    def format_timestamp(self) -> datetime:
        """Format the timestamp string to a datetime object."""
        return datetime.strptime(self.timestamp, "%Y-%m-%d %H:%M")

    @property
    def content_markdown(self) -> str:
        """Get message content as markdown."""
        if self.content_html is None:
            raise ValueError("Message content is not available")
        return html_to_markdown(self.content_html)


@dataclass
class MessagesList:
    """List of messages response."""

    messages: List[Message] = field(default_factory=list)
