"""Wilma API client.

The client is read-only: login is the only non-GET request it makes, and every data request
goes through ``_get``, which can only issue GET requests.
"""

import datetime
import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import aiohttp

from wilhelmina.models import (
    AttendanceRange,
    AttendanceReport,
    Lesson,
    Message,
    MessageFolder,
    Role,
    ScheduleGroup,
    Term,
    WeekSchedule,
)
from wilhelmina.models.news import Bulletin
from wilhelmina.parsers.attendance import parse_attendance_html
from wilhelmina.parsers.news import parse_bulletin, parse_bulletin_list

logger = logging.getLogger(__name__)

# Redirect targets and URL fragments Wilma uses when the session is no longer valid.
_SESSION_EXPIRED_MARKERS = ("sessionexpired", "invalidsession")
_SESSION_EXPIRED_STATUSES = (401, 403)

# Patterns for finding the user ID (e.g. "!1234567") in the home page HTML.
_USER_ID_PATTERNS = (
    re.compile(r'["\'/](![\w\d]+)["\'/]'),
    re.compile(r'user[Ii]d["\']?\s*[:=]\s*["\']?(![\w\d]+)'),
)

_REDIRECT_STATUSES = (301, 302, 303, 307, 308)

# Role types whose user ID gives access to a student's data
_STUDENT_ROLE_TYPES = ("guardian", "student")

# Fetching full content marks messages as read server-side, so bulk fetches need an
# explicit opt-in above this size.
_CONTENT_FETCH_LIMIT = 10


class WilmaError(Exception):
    """Base exception for Wilma API errors."""


class AuthenticationError(WilmaError):
    """Authentication error."""


class WilmaClient:
    """Read-only client for the Wilma API."""

    def __init__(
        self,
        base_url: str,
        session: Optional[aiohttp.ClientSession] = None,
        debug: bool = False,
        headless: bool = True,
        timezone: str = "Europe/Helsinki",
    ) -> None:
        """Initialize the client.

        Args:
            base_url: Wilma instance URL, e.g. ``https://turku.inschool.fi``.
            session: Optional aiohttp session to reuse. It is not closed by the client.
            debug: Enable debug logging.
            headless: Deprecated and ignored; kept for backwards compatibility.
            timezone: IANA timezone the Wilma instance reports its timestamps in.
        """
        self.base_url = base_url.rstrip("/")
        self.session = session
        self.user_id: Optional[str] = None
        self._sid: Optional[str] = None
        self.debug = debug
        self.headless = headless
        self.timezone = ZoneInfo(timezone)
        self._primus_ids: dict[str, int] = {}
        self._owns_session = session is None
        self.username: str | None = None
        self.password: str | None = None

        if debug:
            logger.setLevel(logging.DEBUG)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure that a session exists."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
            self._owns_session = True
        return self.session

    async def close(self) -> None:
        """Close the HTTP session if we created it."""
        if self._owns_session and self.session and not self.session.closed:
            await self.session.close()
            self.session = None

    async def __aenter__(self) -> "WilmaClient":
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _check_auth(self) -> None:
        """Check if authenticated and raise error if not."""
        if not self.user_id or not self._sid:
            logger.debug("Not authenticated")
            raise AuthenticationError("Not authenticated")

    ################################
    # Authentication
    ################################

    async def login(self, username: str | None = None, password: str | None = None) -> None:
        """Login to Wilma.

        Wilma allows a single active session per account: logging in invalidates every
        other session for the same user, including browser and mobile app sessions.
        """
        self.username = username or self.username
        self.password = password or self.password

        if not self.username or not self.password:
            raise AuthenticationError("Username and password must be provided")

        session = await self._ensure_session()
        logger.debug("Logging in to %s as %s", self.base_url, self.username)

        # Get SESSIONID token
        async with session.get(f"{self.base_url}/token") as response:
            if response.status != 200:
                raise AuthenticationError(f"Failed to get token: {response.status}")

            login_id = response.cookies.get("Wilma2LoginID")
            if not login_id:
                raise AuthenticationError("No login ID cookie found")

            session_id = login_id.value
            logger.debug("Got session ID: %s", session_id)

        data = {
            "Login": self.username,
            "Password": self.password,
            "SESSIONID": session_id,
        }

        async with session.post(
            f"{self.base_url}/login", data=data, allow_redirects=False
        ) as response:
            if response.status != 302 and response.status != 303:
                raise AuthenticationError(f"Login failed: {response.status}")

            sid = response.cookies.get("Wilma2SID")
            if not sid:
                raise AuthenticationError("No SID cookie found")

            self._sid = sid.value

            location = response.headers.get("Location")
            if not location:
                raise AuthenticationError("No Location header in response")

        # Some instances redirect to a checkcookie page without the user ID in the URL
        if "checkcookie" in location and "!" not in location:
            user_id, location = await self._resolve_checkcookie_redirect(session, location)
            if user_id:
                self.user_id = user_id
                logger.debug("Logged in as %s", self.user_id)
                return

        if "!" not in location:
            raise AuthenticationError(f"Invalid Location header: {location}")

        self.user_id = "!" + location.split("!")[1].split("?")[0]
        logger.debug("Logged in as %s", self.user_id)

    async def _resolve_checkcookie_redirect(
        self, session: aiohttp.ClientSession, location: str
    ) -> tuple[str | None, str]:
        """Follow a checkcookie redirect.

        Returns ``(user_id, location)``: the user ID when it had to be read from the home
        page, otherwise None and the redirect target, which carries the user ID.
        """
        logger.debug("Following checkcookie redirect: %s", location)
        async with session.get(location, allow_redirects=False) as response:
            logger.debug("Checkcookie response status: %s", response.status)
            if response.status not in _REDIRECT_STATUSES:
                logger.debug("No redirect from checkcookie, reading user ID from home page")
                return await self._extract_user_id_from_home_page(session), location

            new_location = response.headers.get("Location")
            if not new_location:
                raise AuthenticationError("No Location header in checkcookie redirect")

        if "!" not in new_location and new_location.rstrip("/") == self.base_url:
            logger.debug("Redirect to root, reading user ID from home page")
            return await self._extract_user_id_from_home_page(session), new_location

        logger.debug("Got redirect location: %s", new_location)
        return None, new_location

    async def _extract_user_id_from_home_page(self, session: aiohttp.ClientSession) -> str:
        """Extract the user ID from the logged-in home page HTML."""
        async with session.get(self.base_url) as response:
            if response.status != 200:
                raise AuthenticationError(f"Failed to load home page: {response.status}")
            content = await response.text()

        for pattern in _USER_ID_PATTERNS:
            match = pattern.search(content)
            if match:
                logger.debug("Extracted user ID from home page: %s", match.group(1))
                return match.group(1)

        raise AuthenticationError(
            "Could not extract user ID from home page after checkcookie redirect"
        )

    ################################
    # Requests
    ################################

    @staticmethod
    def _is_login_url(url: str) -> bool:
        if any(marker in url for marker in _SESSION_EXPIRED_MARKERS):
            return True
        return urlparse(url).path.rstrip("/").endswith("/login")

    @classmethod
    def _is_session_expired(cls, response: aiohttp.ClientResponse) -> bool:
        """Whether a response indicates the session is no longer valid."""
        if response.status in _SESSION_EXPIRED_STATUSES:
            return True
        # Requests made with an invalid session are redirected to the login page
        if response.status in _REDIRECT_STATUSES:
            return cls._is_login_url(response.headers.get("Location", ""))
        return False

    @staticmethod
    async def _error_detail(response: aiohttp.ClientResponse) -> str:
        """Human-readable error from Wilma's JSON error body, if there is one."""
        try:
            data = await response.json(content_type=None)
        except aiohttp.ClientError, ValueError:
            return ""
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            return str(error.get("description") or error.get("message") or "")
        return ""

    async def _get(
        self,
        path: str,
        params: dict[str, str] | None = None,
        *,
        as_json: bool = True,
        user_scoped: bool = True,
        user_id: str | None = None,
        retry_on_expired_session: bool = True,
    ) -> Any:
        """GET a resource under a user root (``/<user_id>/<path>``), or under the site root
        when ``user_scoped`` is false. ``user_id`` defaults to the logged-in user ID.

        This is the only method that requests data from Wilma, and it only issues GET
        requests, which keeps the client read-only. Redirects are not followed: data
        endpoints answer directly, and an invalid session redirects to the login page,
        which can redirect to itself indefinitely.
        """
        self._check_auth()
        session = await self._ensure_session()
        root = f"{self.base_url}/{user_id or self.user_id}" if user_scoped else self.base_url
        url = f"{root}/{path.lstrip('/')}"
        headers = {"Wilma2SID": self._sid or ""}

        logger.debug("GET %s params=%s", url, params)
        try:
            async with session.get(
                url, headers=headers, params=params, allow_redirects=False
            ) as response:
                if not self._is_session_expired(response):
                    return await self._read_body(response, url, as_json)
                status = response.status
                detail = await self._error_detail(response)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise WilmaError(f"Request to {url} failed: {err!r}") from err

        if retry_on_expired_session:
            logger.debug("Session expired, logging in again")
            await self.login()
            return await self._get(
                path,
                params,
                as_json=as_json,
                user_scoped=user_scoped,
                user_id=user_id,
                retry_on_expired_session=False,
            )

        if status == 403:
            raise WilmaError(f"Access denied to {url}: {detail}".rstrip(": "))
        raise AuthenticationError(f"Session expired and re-login did not help: {url}")

    @staticmethod
    async def _read_body(response: aiohttp.ClientResponse, url: str, as_json: bool) -> Any:
        if response.status in _REDIRECT_STATUSES:
            location = response.headers.get("Location", "")
            raise WilmaError(f"Unexpected redirect from {url} to {location}")
        if response.status >= 400:
            raise WilmaError(f"Request failed with status {response.status}: {url}")
        if not as_json:
            return await response.text()
        try:
            return await response.json()
        except (aiohttp.ContentTypeError, ValueError) as err:
            raise WilmaError(f"Expected JSON from {url}: {err}") from err

    async def _get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
        *,
        user_scoped: bool = True,
        user_id: str | None = None,
    ) -> Any:
        """GET a JSON resource under a user root (or the site root)."""
        return await self._get(path, params, user_scoped=user_scoped, user_id=user_id)

    async def _get_text(
        self, path: str, params: dict[str, str] | None = None, *, user_id: str | None = None
    ) -> str:
        """GET an HTML page under a user root."""
        text: str = await self._get(path, params, as_json=False, user_id=user_id)
        return text

    ################################
    # Messages
    ################################

    async def get_messages(
        self,
        only_unread: bool = False,
        after: datetime.datetime | None = None,
        with_content: bool = False,
        no_message_content_fetch_limit: bool = False,
        folder: MessageFolder = MessageFolder.INBOX,
        user_id: str | None = None,
    ) -> list[Message]:
        """Get all messages in a folder, newest first.

        Listing messages does not change their read status. ``unread`` reflects the state
        at the time of listing.

        Args:
            only_unread: Only return unread messages.
            after: Only return messages newer than this. Wilma timestamps are naive local
                time in the client's ``timezone``; a timezone-aware value is converted to
                that timezone first, a naive value is assumed to already be in it.
            with_content: Also fetch each message's full content. This marks every fetched
                message as read in Wilma.
            no_message_content_fetch_limit: Allow ``with_content`` for more than 10 messages.
            folder: Which folder to list.
            user_id: Whose messages to list, e.g. another child's user ID from
                ``get_students()``. Defaults to the logged-in user ID.
        """
        data = await self._get_json(folder.list_path, user_id=user_id)

        if after and after.tzinfo is not None:
            after = after.astimezone(self.timezone).replace(tzinfo=None)

        messages = []
        for msg in data.get("Messages", []):
            message = Message.from_dict(msg)

            if only_unread and not message.unread:
                continue

            if after and message.timestamp and message.format_timestamp() <= after:
                continue

            messages.append(message)

        if with_content:
            await self.fetch_content(messages, no_message_content_fetch_limit, user_id=user_id)

        return messages

    async def fetch_content(
        self,
        messages: list[Message],
        no_message_content_fetch_limit: bool = False,
        *,
        user_id: str | None = None,
    ) -> None:
        """Fetch full content and replies into listed messages, in place.

        List-only fields such as ``unread`` keep their listed values. A message whose
        content cannot be fetched is left without content. This marks every fetched message
        as read in Wilma.
        """
        if len(messages) > _CONTENT_FETCH_LIMIT:
            if not no_message_content_fetch_limit:
                raise WilmaError(
                    f"Not allowed to fetch full message content for more than "
                    f"{_CONTENT_FETCH_LIMIT} messages. "
                    "Set no_message_content_fetch_limit=True to override this limit."
                )
            logger.warning(
                "Fetching full message content for %s messages may take a while..",
                len(messages),
            )

        for message in messages:
            try:
                full = await self.get_message_content(message.id, user_id=user_id)
            except WilmaError as e:
                logger.warning("Failed to fetch content for message %s: %s", message.id, e)
                continue

            message.content_html = full.content_html
            message.reply_list = full.reply_list
            message.allow_forward = full.allow_forward
            message.allow_reply = full.allow_reply
            if full.recipients:
                message.recipients = full.recipients
            for attr in ("recipient", "recipient_count"):
                if getattr(message, attr) is None:
                    setattr(message, attr, getattr(full, attr))

    async def get_message_content(self, message_id: int, user_id: str | None = None) -> Message:
        """Get a single message with its full content and replies.

        This marks the message as read in Wilma. Wilma has no way to mark a message unread
        again.
        """
        data = await self._get_json(
            f"messages/{message_id}", params={"format": "json"}, user_id=user_id
        )

        try:
            return Message.from_dict(data["messages"][0])
        except (KeyError, IndexError, TypeError) as err:
            raise WilmaError(f"Unexpected message response for {message_id}") from err

    ################################
    # Attendance
    ################################

    async def get_attendance(
        self,
        period: AttendanceRange | int = AttendanceRange.SCHOOL_YEAR,
        start: datetime.date | None = None,
        end: datetime.date | None = None,
        user_id: str | None = None,
    ) -> AttendanceReport:
        """Get lesson marks: absences, lateness, positive feedback, homework, behaviour etc.

        Args:
            period: A predefined range of the attendance view, or a period number.
            start: First day of a custom range. Requires ``end``; overrides ``period``.
            end: Last day of a custom range. Requires ``start``.
            user_id: Whose marks to get. Defaults to the logged-in user ID.

        Returns:
            The marks in the range, and every mark type the school has configured, with the
            colours Wilma shows them in.
        """
        if start is not None or end is not None:
            if start is None or end is None:
                raise ValueError("start and end must be given together")
            if start > end:
                raise ValueError("start must not be after end")
            params = {
                "range": str(int(AttendanceRange.CUSTOM)),
                "first": f"{start.day}.{start.month}.{start.year}",
                "last": f"{end.day}.{end.month}.{end.year}",
            }
        elif period == AttendanceRange.CUSTOM:
            raise ValueError("A custom range requires start and end")
        else:
            params = {"range": str(int(period))}

        html = await self._get_text("attendance/view", params=params, user_id=user_id)
        return parse_attendance_html(html)

    ################################
    # Bulletins
    ################################

    async def get_bulletins(self, user_id: str | None = None) -> list[Bulletin]:
        """Bulletins on the school's bulletin board: current ones (newest first), then pinned
        and older ones. Listed bulletins have no content; use ``get_bulletin`` for that.

        Args:
            user_id: Whose bulletin board to read. Defaults to the logged-in user ID.
        """
        html = await self._get_text("news", user_id=user_id)
        return parse_bulletin_list(html, self.today())

    async def get_bulletin(self, news_id: int, user_id: str | None = None) -> Bulletin:
        """A single bulletin with its content. Reading bulletins does not change any state."""
        html = await self._get_text(f"news/{news_id}", user_id=user_id)
        return parse_bulletin(html, news_id, self.today())

    ################################
    # Roles and schedule
    ################################

    async def get_roles(self) -> list[Role]:
        """Roles of the logged-in account, e.g. one guardian role per child."""
        data = await self._get_json("api/v1/accounts/me/roles", user_scoped=False)
        payload = data.get("payload") if isinstance(data, dict) else None
        if not isinstance(payload, list):
            raise WilmaError("Unexpected roles response")
        return [Role.from_dict(role) for role in payload if isinstance(role, dict)]

    async def get_students(self) -> list[Role]:
        """The students the account can see: its guardian roles, or its own student role.

        Pass a student's ``user_id`` to the data methods to get that student's data.
        """
        return [
            role
            for role in await self.get_roles()
            if role.user_id and role.type in _STUDENT_ROLE_TYPES
        ]

    async def _primus_id(self, user_id: str | None = None) -> int:
        """Numeric ID of the person a user ID refers to (e.g. the student)."""
        self._check_auth()
        user_id = user_id or self.user_id or ""
        if user_id not in self._primus_ids:
            for role in await self.get_roles():
                if role.user_id:
                    self._primus_ids[role.user_id] = role.primus_id
            if user_id not in self._primus_ids:
                raise WilmaError(f"No role found for {user_id}")
        return self._primus_ids[user_id]

    def today(self) -> datetime.date:
        """Today's date in the Wilma instance's timezone."""
        return datetime.datetime.now(self.timezone).date()

    async def get_schedule(
        self, day: datetime.date | None = None, user_id: str | None = None
    ) -> WeekSchedule:
        """Get the lessons of the Monday-to-Sunday week containing ``day``.

        The schedule reflects the actual week: holidays and other days off have no lessons.

        Args:
            day: Any date in the wanted week. Defaults to today.
            user_id: Whose schedule to get. Defaults to the logged-in user ID.
        """
        day = day or self.today()
        week_start = day - datetime.timedelta(days=day.weekday())
        primus_id = await self._primus_id(user_id)
        data = await self._get_json(
            f"schedule/export/students/{primus_id}",
            params={"date": f"{day.day}.{day.month}.{day.year}", "getfullweek": "true"},
            user_id=user_id,
        )
        if not isinstance(data, dict):
            raise WilmaError("Unexpected schedule response")

        try:
            lessons = [_parse_lesson(item, week_start) for item in data.get("Schedule") or []]
            terms = [Term.from_dict(term) for term in data.get("Terms") or []]
        except (KeyError, TypeError, ValueError) as err:
            raise WilmaError(f"Unexpected schedule response: {err}") from err

        lessons.sort(key=lambda lesson: (lesson.date, lesson.start))
        return WeekSchedule(week_start=week_start, lessons=lessons, terms=terms)


def _parse_lesson(item: dict[str, Any], week_start: datetime.date) -> Lesson:
    """Build a lesson from a schedule entry, whose ``Day`` is the ISO weekday."""
    return Lesson(
        date=week_start + datetime.timedelta(days=int(item["Day"]) - 1),
        start=datetime.time.fromisoformat(item["Start"]),
        end=datetime.time.fromisoformat(item["End"]),
        groups=[ScheduleGroup.from_dict(group) for group in item.get("Groups") or []],
        class_name=item.get("Class"),
        color=item.get("Color"),
        reservation_id=item.get("ReservationID"),
        schedule_id=item.get("ScheduleID"),
    )
