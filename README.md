# Wilhelmina - Wilma API Client

A Python API client for the Wilma school platform. This client allows you to authenticate, fetch messages, and view message contents from the Wilma platform.

Why is this not called Wilma? The reason is simple, PyPi sees "Wilma" as a prohibited packages name. It
is not taken on PyPi, it just is not allowed. Wilhelmina is the long/full version of the name Wilma which
is the reason for the name.

## Wilma API Features

The client is **read-only**: logging in is the only non-GET request it makes.

- [X] Messages
  - [X] List all messages in a folder (inbox, archive, outbox, drafts, appointments)
  - [X] Unread status (from the list endpoint's `Status` field)
  - [X] Get a single message with content and replies
- [X] Lesson marks ("Lektionsanteckningar" / "Tuntimerkinnät")
  - [X] Absences, lateness, positive feedback, missing homework, behaviour notes, etc.
  - [X] Mark types with code, description and Wilma's colour for each
  - [X] Predefined ranges (four weeks, autumn, spring, periods, school year) or any date range
- [X] Schedule
  - [X] Lessons of any Monday-to-Sunday week (holidays and days off included), with
        subject, teachers, rooms and times
  - [X] School terms
- [X] Roles of the account (e.g. one guardian role per child)

### Things to know about Wilma

- **Opening a message marks it as read.** `get_message_content()` and
  `get_messages(with_content=True)` mark every fetched message as read in Wilma, and Wilma has
  no way to mark a message unread again. Listing messages does not change read status.
- **One session per account.** Logging in invalidates all other sessions for the same user
  (browser, mobile app, other clients). The client logs in again by itself if its own
  session gets invalidated.
- The list endpoints return every message in the folder in a single response; the
  pagination in the web UI is client-side only.
- Lesson marks have no JSON endpoint; they are parsed from the attendance view's HTML.
- Timestamps are naive Finnish local time. Timezone-aware `after=` values are converted to
  the client's `timezone` (default `Europe/Helsinki`).

## Home Assistant compatibility

This library has support for passing in an existing `aiohttp` to allow for easier integration with
Home Assistant. The version of `aiohttp` has also been slightly restricted in order to be installable
in Home Assistant. `mashumaro` was chosen for type safe models instead of Pydantic to not need to
go through the v1 vs. v2 hassle.

## Note about AI

Sonnet 3.7 has written a lot code in this repository. Far from one-shotted however and a lot of
refactoring has been done in order to get things into this state. The main purpose for creating
this library was to get quick access to the Wilma API through Python.

## Installation

```bash
pip install wilhelmina

# Using Poetry
poetry add wilhelmina
```

## API Client Usage

```python
import asyncio
import datetime

from wilhelmina import AttendanceRange, MessageFolder, WilmaClient


async def main():
    # Optionally pass in an existing aiohttp session; it will not be closed by the client
    async with WilmaClient("https://turku.inschool.fi") as client:
        await client.login("username", "password")

        # All inbox messages, newest first. Does not change read status.
        messages = await client.get_messages()
        for msg in messages:
            status = "UNREAD" if msg.unread else "read"
            print(f"{msg.id}: {msg.subject} - {msg.timestamp} - {msg.sender} - {status}")

        # Only unread messages
        unread = await client.get_messages(only_unread=True)

        # Other folders
        sent = await client.get_messages(folder=MessageFolder.OUTBOX)

        # Full content and replies. NOTE: this marks the message as read in Wilma.
        if unread:
            content = await client.get_message_content(unread[0].id)
            print(content.content_markdown)
            for reply in content.reply_list:
                print(reply.sender, reply.content_markdown)

        # Lesson marks for the school year (or AttendanceRange.FOUR_WEEKS, start=/end=, ...)
        report = await client.get_attendance(AttendanceRange.SCHOOL_YEAR)
        for mark in report.marks:
            print(mark.date, mark.hour, mark.type.code, mark.type.color, mark.course, mark.comment)

        # Mark types are configured per school; e.g. positive feedback uses the code "+"
        positive = report.marks_with_code("+")
        latest = report.latest  # mark on the latest date and hour

        # Each mark has a stable `key` (Wilma has no mark IDs), e.g. to detect new marks
        seen: set[str] = set()  # persist this between runs
        new_marks = [m for m in report.marks if m.key not in seen]

        # Schedule: the week containing a date (default today)
        week = await client.get_schedule()
        for lesson in week.lessons_on(client.today()):
            print(lesson.start, lesson.end, lesson.subject, lesson.teachers, lesson.rooms)
        next_week = await client.get_schedule(week.week_start + datetime.timedelta(days=7))

        # List first, then fetch content only for the messages you need (marks them read)
        messages = await client.get_messages()
        await client.fetch_content(messages[:3])


asyncio.run(main())
```

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/frwickst/pywilma.git
cd wilhelmina

# Install development dependencies
poetry install
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run specific tests
poetry run pytest wilhelmina/tests/test_client.py

# Run with coverage
poetry run pytest --cov=wilhelmina
```

### Linting and Type Checking

```bash
# Format with ruff
poetry run ruff format wilhelmina

# Run ruff for linting
poetry run ruff check wilhelmina --fix

# Run mypy for type checking
poetry run mypy wilhelmina
```

## License

MIT
