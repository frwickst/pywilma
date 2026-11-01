"""Tests for bulletin parsing and fetching."""

import datetime
from unittest.mock import AsyncMock

import pytest

from wilhelmina import Bulletin, BulletinSection, WilmaClient, WilmaError
from wilhelmina.parsers.news import parse_bulletin, parse_bulletin_list

TODAY = datetime.date(2026, 11, 1)

# Mirrors the bulletin board: a pinned panel, the older-bulletins panel rendered twice for
# different screen sizes, and the current panel with date headings.
LIST_HTML = """
<html><body><main>
<div class="panel"><div class="panel-body">
  <h2>Pinned notices</h2>
  <div class="margin-bottom-inline"><a class="link-with-arrow" href="/!12345/news/100">Pinned one</a></div>
  <div class="margin-bottom-inline"><a class="link-with-arrow" href="/!12345/news/300">Also current</a></div>
</div></div>
<div class="panel hidden-sm-down"><div class="panel-body">
  <h2>Older notices</h2>
  <div class="margin-bottom-inline"><a href="/!12345/news/50">Old one</a></div>
</div></div>
<div class="panel tab-content"><div class="panel-body">
  <h2 class="no-border">19.10.</h2>
  <div class="margin-bottom well">
    <h3> Autumn concert </h3>
    <span class="horizontal-link-container small">
      <a href="/!12345/news/300">Read the full notice</a>
      <a href="/!12345/profiles/teachers/1" class="profile-link" title="Anna Teacher">atea</a>
    </span>
  </div>
  <h2 class="no-border">24.12.</h2>
  <div class="margin-bottom well">
    <h3>Last year's party</h3>
    <span class="horizontal-link-container small">
      <a href="/!12345/news/200">Read the full notice</a>
      <span class="tooltip" title="Bo Principal">B.P</span>
    </span>
  </div>
  <div class="margin-bottom well"><h3>No link</h3></div>
</div></div>
<div class="panel hidden-md-up"><div class="panel-body">
  <h2>Older notices</h2>
  <div class="margin-bottom"><a href="/!12345/news/50">Old one</a></div>
  <div class="margin-bottom"><a href="/!12345/news/abc">Not a bulletin</a></div>
</div></div>
</main></body></html>
"""

ITEM_HTML = """
<html><body><main><div class="panel"><div class="panel-body">
  <h2> Autumn concert </h2>
  <p><strong>Lead paragraph</strong></p>
  <div class="margin-bottom hidden" id="news-content"><p>Welcome to the <em>concert</em>.</p></div>
  <div class="panel-body-padding-remover"><iframe id="content-wrapper"></iframe></div>
  <hr/>
  <div class="margin-bottom"> Public, guardians and students </div>
  <div class="horizontal-link-container">
    <span class="vismaicon vismaicon-sm vismaicon-user"></span>
    <span> atea (Anna Teacher) </span>
    <span class="small semi-bold no-side-margin pull-right">Published 19.10.</span>
  </div>
</div></div></main></body></html>
"""


def test_parse_bulletin_list() -> None:
    bulletins = parse_bulletin_list(LIST_HTML, TODAY)

    assert [(b.id, b.section) for b in bulletins] == [
        (300, BulletinSection.CURRENT),
        (200, BulletinSection.CURRENT),
        (100, BulletinSection.PERMANENT),
        (50, BulletinSection.OLD),
    ]
    concert = bulletins[0]
    assert concert.title == "Autumn concert"
    assert concert.date == datetime.date(2026, 10, 19)
    assert concert.author == "Anna Teacher"
    assert concert.content_html is None
    # A date later in the year than today belongs to the previous year
    assert bulletins[1].date == datetime.date(2025, 12, 24)
    assert bulletins[1].author == "Bo Principal"
    assert bulletins[2].date is None


def test_parse_bulletin_list_empty() -> None:
    assert parse_bulletin_list("<html><body><main></main></body></html>", TODAY) == []


def test_parse_bulletin() -> None:
    bulletin = parse_bulletin(ITEM_HTML, 300, TODAY)

    assert bulletin.id == 300
    assert bulletin.title == "Autumn concert"
    assert bulletin.date == datetime.date(2026, 10, 19)
    assert bulletin.author == "atea (Anna Teacher)"
    assert bulletin.audience == "Public, guardians and students"
    assert "Lead paragraph" in bulletin.content_html
    assert "<em>concert</em>" in bulletin.content_html
    assert bulletin.content_markdown.startswith("**Lead paragraph**")


def test_parse_bulletin_with_full_date() -> None:
    html = ITEM_HTML.replace("Published 19.10.", "Published 23.2.2023")
    assert parse_bulletin(html, 300, TODAY).date == datetime.date(2023, 2, 23)


def test_bulletin_without_content() -> None:
    with pytest.raises(ValueError, match="not available"):
        _ = Bulletin(id=1, title="x").content_markdown


def _client() -> WilmaClient:
    client = WilmaClient("https://test.inschool.fi")
    client.user_id = "!12345"
    client._sid = "sid"
    client.today = lambda: TODAY  # type: ignore[method-assign]
    return client


@pytest.mark.asyncio
async def test_get_bulletins() -> None:
    client = _client()
    client._get_text = AsyncMock(return_value=LIST_HTML)

    bulletins = await client.get_bulletins(user_id="!67890")

    client._get_text.assert_awaited_once_with("news", user_id="!67890")
    assert len(bulletins) == 4


@pytest.mark.asyncio
async def test_get_bulletin() -> None:
    client = _client()
    client._get_text = AsyncMock(return_value=ITEM_HTML)

    bulletin = await client.get_bulletin(300)

    client._get_text.assert_awaited_once_with("news/300", user_id=None)
    assert bulletin.title == "Autumn concert"


@pytest.mark.asyncio
async def test_get_bulletins_error_propagates() -> None:
    client = _client()
    client._get_text = AsyncMock(side_effect=WilmaError("down"))

    with pytest.raises(WilmaError):
        await client.get_bulletins()
