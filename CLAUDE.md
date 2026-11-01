# CLAUDE.md for Wilma Client

This file contains information for Claude Code to help with working on this project.

## Project Overview

This project is an API client for the Wilma school platform. It allows authentication, fetching messages, and viewing message contents from the Wilma platform. This is the core library package that can be used by other applications.

## Project Structure

- `wilhelmina/` - Main package
  - `__init__.py` - Package exports
  - `client.py` - Main API client implementation
  - `models/` - Data models
    - `__init__.py` - Model exports
    - `messages.py` - Message-related data models
    - `attendance.py` - Lesson mark (attendance) models
    - `schedule.py` - Schedule and role models
    - `news.py` - Bulletin models
  - `parsers/` - HTML parsers for pages without a JSON endpoint
    - `attendance.py` - Attendance view parser
    - `news.py` - Bulletin board and bulletin parsers
  - `tests/` - Test suite
    - `__init__.py`
    - `conftest.py` - Pytest configuration
    - `test_client.py` - Tests for API client
    - `test_models.py` - Tests for data models
    - `test_error_handling.py` - Tests for error paths
    - `test_attendance.py` - Tests for attendance parsing and fetching
    - `test_schedule.py` - Tests for roles and schedule
    - `test_news.py` - Tests for bulletins
    - `test_utils.py` - Tests for utilities
  - `utils/` - Utility functions
    - `__init__.py` - Utility exports

## Development Commands

Run these commands to verify your code before committing:

```bash
# Format with ruff
poetry run ruff format wilhelmina

# Lint with ruff
poetry run ruff check wilhelmina --fix

# Type check with mypy
poetry run mypy wilhelmina

# Run tests
poetry run pytest
```

Poetry is configured not to create virtualenvs; a project-local `.venv` (gitignored) works:
`uv venv -p 3.14 .venv && VIRTUAL_ENV=$PWD/.venv POETRY_VIRTUALENVS_CREATE=true poetry install`

## API Authentication Flow

1. Call `GET https://turku.inschool.fi/token` to get a `Wilma2LoginID` cookie
2. Use that cookie as the `SESSIONID` parameter when posting to `https://turku.inschool.fi/login`
3. From the login response, get:
   - A `Wilma2SID` cookie for future authentication
   - The user ID from the `Location` header (format: `/!04354289?checkcookie`)
4. Include the `Wilma2SID` header in all subsequent requests

## Read-only Policy

The library is read-only. Login (`POST /login`) is the only non-GET request allowed. Never add
or call an endpoint that could perform an action (sending, replying, approving, registering,
deleting, archiving, etc.) without explicit approval from the maintainer. All data requests
go through `WilmaClient._get_json`, which only issues GET requests.

## API Endpoints

- `GET /<USERID>/messages/list` - Inbox; returns all messages in one response
- `GET /<USERID>/messages/list/{archive,outbox,drafts,appointments}` - Other folders
- `GET /<USERID>/messages/<MESSAGEID>?format=json` - Message content and `ReplyList`.
  **Side effect: marks the message as read** (cannot be undone)

- `GET /<USERID>/attendance/view?range=<n>` - Lesson marks, **HTML only** (parsed). Ranges:
  `0` four weeks, `-1` autumn, `-2` spring, `1`/`2`.. periods, `-4` school year,
  `-3&first=d.m.yyyy&last=d.m.yyyy` custom (also works for previous school years)
- `GET /<USERID>/schedule/export/students/<primusId>?date=d.m.yyyy&getfullweek=true` - JSON
  lessons of the Mon-Sun week containing `date` (`Day` = ISO weekday; holidays are empty),
  plus `Terms`
- `GET /api/v1/accounts/me/roles` - JSON roles of the account (site root, not under the user
  ID); maps a role's `slug` (`/!<USERID>`) to its `primusId`. Payload also has a `formKey`
  (form token) which the library deliberately drops
- `GET /<USERID>/news` - Bulletin board, **HTML only** (parsed). Current bulletins under date
  headings (`19.10.`, no year), plus link-only panels for pinned and older bulletins; the
  older panel is rendered twice (`hidden-sm-down` / `hidden-md-up`), which tells it apart from
  the pinned one regardless of language. `news/index_json` is 403 for guardians.
- `GET /<USERID>/news/<ID>` - Single bulletin, HTML: `#news-content` body, published date
  (year omitted for recent ones), author and audience
- `GET /<USERID>/overview` - JSON with this week's schedule, exams and groups (not used yet)

Every user-scoped data method takes `user_id`; a guardian account has one user ID per child
(`get_students()`), and the same session can read all of them.

List entries carry `Status: 1` when unread; read messages omit `Status`.

Attendance view: each mark is `td.event.at-tp<ID>` with a `title` like
`course; name[; comment] /Teacher[ - d.m. /Clarifier]` (course may be missing). The legend
(`.legend`) maps type IDs to code/description; inline `<style>` holds each type's colour.
Overlapping marks continue on extra rows without a date.
Marks have no Wilma ID; `AttendanceMark.key` (date|hour|type|course|teacher code|name, plus
`#n` for identical marks) is the stable identity the Home Assistant integration uses to detect
new marks. Don't change the key format without considering that stored keys would all look new.

## Related Projects

- `../wilma_ha` - Home Assistant integration built on this library (pins an exact version)
- `../wilhelminacli` - CLI built on this library

## Wilma Behavior

- Only one session per account: logging in invalidates all other sessions for that user
- An invalidated session redirects requests to `/login?invalidsession&returnpath=...`, which can
  redirect to itself forever, so `_get` never follows redirects; it re-logs in once instead
- 401 means re-login needed; 403 can mean either an invalid session or no permission
- Timestamps are naive Europe/Helsinki local time

## Data Models

- `Message` - A message (list metadata, plus content/replies when fetched individually)
- `MessageFolder` - Folder enum mapping to the list endpoints
- `Reply` - A reply in a message thread
- `MessagesList` - Container for a list of messages
- `Sender` - Information about the sender of a message
- `AttendanceReport` - Lesson marks plus the school's mark types
- `AttendanceMark` - A single lesson mark
- `MarkType` - Mark type from the legend (code, description, colour)
- `AttendanceRange` - Predefined attendance view ranges
- `WeekSchedule` / `Lesson` / `ScheduleGroup` / `Term` - Schedule of a week
- `Role` - A role of the logged-in account
- `Bulletin` / `BulletinSection` - A bulletin and where it is listed

## Common Issues and Solutions

- Authentication issues: Ensure correct cookie handling and header extraction
- JSON parsing errors: The API sometimes returns malformed JSON
- Cookie handling: Ensure cookies are properly extracted and passed
