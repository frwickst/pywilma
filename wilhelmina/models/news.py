"""Bulletin (news) models for Wilma."""

import datetime
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from mashumaro import DataClassDictMixin

from wilhelmina.utils import html_to_markdown


class BulletinSection(StrEnum):
    """Where a bulletin is listed on the bulletin board."""

    CURRENT = "current"
    """Recent bulletins, listed with their date."""
    PERMANENT = "permanent"
    """Bulletins the school keeps pinned."""
    OLD = "old"
    """Older bulletins."""


@dataclass
class Bulletin(DataClassDictMixin):
    """A bulletin from the school's bulletin board.

    Listed bulletins carry the title, section and (for current ones) date. ``content_html``,
    ``audience`` and the published date are filled in when a single bulletin is fetched.
    """

    id: int
    title: str
    section: Optional[BulletinSection] = None
    date: Optional[datetime.date] = None
    author: Optional[str] = None
    audience: Optional[str] = None
    content_html: Optional[str] = None

    @property
    def content_markdown(self) -> str:
        """Bulletin content as markdown."""
        if self.content_html is None:
            raise ValueError("Bulletin content is not available")
        return html_to_markdown(self.content_html)
