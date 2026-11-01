"""Message models for Wilma API."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import List, Optional

from mashumaro import DataClassDictMixin
from mashumaro.config import BaseConfig

from wilhelmina.utils import html_to_markdown

# Value of the list endpoints' ``Status`` field for messages the user has not opened yet.
# Read messages omit the field entirely.
UNREAD_STATUS = 1


class MessageFolder(StrEnum):
    """Message folders, each backed by its own list endpoint."""

    INBOX = "inbox"
    ARCHIVE = "archive"
    OUTBOX = "outbox"
    DRAFTS = "drafts"
    APPOINTMENTS = "appointments"

    @property
    def list_path(self) -> str:
        """Path of the folder's JSON list endpoint, relative to the user root."""
        if self is MessageFolder.INBOX:
            return "messages/list"
        return f"messages/list/{self.value}"


@dataclass
class Sender(DataClassDictMixin):
    """Sender of a message."""

    name: str
    href: Optional[str] = None

    class Config(BaseConfig):
        aliases = {"name": "Name", "href": "Href"}


@dataclass
class Reply(DataClassDictMixin):
    """A reply in a message thread."""

    id: str
    timestamp: str
    sender: str = ""
    sender_id: Optional[int] = None
    sender_type: Optional[int] = None
    content_html: Optional[str] = None

    class Config(BaseConfig):
        aliases = {
            "id": "Id",
            "timestamp": "TimeStamp",
            "sender": "Sender",
            "sender_id": "SenderId",
            "sender_type": "SenderType",
            "content_html": "ContentHtml",
        }

    @property
    def content_markdown(self) -> str:
        """Get reply content as markdown."""
        if self.content_html is None:
            raise ValueError("Reply content is not available")
        return html_to_markdown(self.content_html)


@dataclass
class Message(DataClassDictMixin):
    """A message in Wilma.

    List endpoints return message metadata only; ``content_html`` and ``reply_list`` are
    populated by the single-message endpoint.
    """

    id: int
    subject: str
    timestamp: str
    folder: str
    sender_id: int | None = None
    sender_type: int | None = None
    sender: str = ""
    content_html: str | None = None
    allow_forward: bool = True
    allow_reply: bool = True
    reply_list: List[Reply] = field(default_factory=list)
    senders: List[Sender] = field(default_factory=list)
    status: int | None = None
    replies: int = 0
    recipient: str | None = None
    recipient_count: int | None = None
    recipients: List[str] = field(default_factory=list)
    sender_student_name: str | None = None
    sender_guardian_name: str | None = None
    is_event: bool = False
    applying: dict[str, str] | None = None
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
            "status": "Status",
            "replies": "Replies",
            "recipient": "Recipient",
            "recipient_count": "RecipientCount",
            "recipients": "Recipients",
            "sender_student_name": "SenderStudentName",
            "sender_guardian_name": "SenderGuardianName",
            "is_event": "IsEvent",
            "applying": "Applying",
            # unread is derived from status, not read from the API
        }

    def __post_init__(self) -> None:
        if self.status is not None:
            self.unread = self.status == UNREAD_STATUS

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
