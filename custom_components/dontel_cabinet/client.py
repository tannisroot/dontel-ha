"""Asynchronous client for the ДонТел personal cabinet (carbon-billing).

The cabinet page is only served with account data when the session cookie
identifies a logged-in subscriber. The ISP logs browsers in by client IP: the
page's own JavaScript POSTs ``auto_login=1`` to the billing plugin, which
starts a session for the requesting IP. This client performs the same dance,
which is why no credentials are configured anywhere.
"""

from __future__ import annotations

import logging
import re
from html import unescape
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from aiohttp.cookiejar import CookieJar
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    CABINET_PATH,
    LOGIN_PATH,
    LOGIN_TIMEOUT,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__package__)

# The request must look like the subscriber's own browser hitting the page.
_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.5",
}

# <td>Баланс</td> ... <td>2 589,09</td> inside the "Лицевой счет" table.
# Inline tags around the label are tolerated; the value cell is taken as text.
_BALANCE_ROW_RE = re.compile(
    r"<td[^>]*>\s*(?:<[^>]*>\s*)*Баланс(?:\s*<[^>]*>\s*)*</td>\s*"
    r"<td[^>]*>\s*([^<]+?)\s*</td>",
    re.IGNORECASE | re.DOTALL,
)

# Decimal amount written the Russian way: thousands separated by any kind of
# (non-breaking/thin) space, decimal comma or dot, e.g. "-1 234,56".
_AMOUNT_RE = re.compile(r"[-+]?\d[\d\s\xa0\u2000-\u200b\u202f\u202c]*([.,]\d+)?")

# Markup that the billing plugin renders only for a not-logged-in visitor.
_NOT_LOGGED_IN_MARKERS = (
    "carbon_modules_authorize",
    "ajax_login.php",
)


class DontelCabinetError(HomeAssistantError):
    """Base class for cabinet client errors."""


def async_create_cabinet_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """Create an aiohttp session that can hold cookies for an IP-address host.

    aiohttp's default cookie policy refuses cookies whose domain is an IP
    address (which is how the cabinet is normally reached, e.g. 10.90.1.27),
    so the PHPSESSID cookie from the auto-login POST would be silently
    dropped and every page fetch would look unauthenticated. `unsafe=True`
    lifts exactly that restriction; the session is still the HA-managed one
    (closed with the config entry).
    """
    return async_create_clientsession(hass, cookie_jar=CookieJar(unsafe=True))


class CannotConnect(DontelCabinetError):
    """Unable to reach the cabinet."""


class NotLoggedIn(DontelCabinetError):
    """The cabinet refused the IP-based auto-login."""


class ParseError(DontelCabinetError):
    """The page was fetched but the balance could not be extracted."""


def normalize_cabinet_url(raw: str) -> str:
    """Return a sane absolute URL to the cabinet welcome page.

    Accepts a host, a full URL, or anything in between and always ends with
    the cabinet path, so stored entry data is canonical.
    Raises ValueError for inputs without a usable host.
    """
    raw = raw.strip()
    if not raw:
        raise ValueError("empty URL")
    if "://" not in raw:
        raw = f"http://{raw}"
    parts = urlsplit(raw)
    if not parts.netloc or "." not in parts.netloc.partition(":")[0]:
        raise ValueError(f"no usable host in {raw!r}")
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"unsupported scheme {parts.scheme!r}")
    return urlunsplit((parts.scheme, parts.netloc, CABINET_PATH, "", ""))


def _parse_balance(html: str) -> float | None:
    """Return the Баланс value from a Лицевой счет page, or None if absent."""
    row = _BALANCE_ROW_RE.search(html)
    if row is None:
        return None
    amount = _AMOUNT_RE.search(unescape(row.group(1)))
    if amount is None:
        return None
    digits = re.sub(r"[\s\xa0\u2000-\u200b\u202f\u202c]", "", amount.group(0))
    try:
        return float(digits.replace(",", "."))
    except ValueError:  # pragma: no cover - regex only yields parseable text
        return None


class DontelCabinetClient:
    """Read the subscriber balance from the cabinet."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        timeout: float,
    ) -> None:
        """Init the client; `url` is the full cabinet welcome page URL."""
        self._session = session
        self._url = url
        self._timeout = timeout
        parts = urlsplit(url)
        self._login_url = urlunsplit((parts.scheme, parts.netloc, LOGIN_PATH, "", ""))

    async def async_get_balance(self) -> float:
        """Return the current balance in account currency.

        Fetches the page; if it comes back unauthenticated (which is what a
        bare, cookie-less request looks like), performs the same IP auto-login
        the page's JavaScript does and retries once with the session cookie.
        """
        html = await self._async_get_page()
        balance = _parse_balance(html)
        if balance is None:
            await self._async_auto_login()
            html = await self._async_get_page()
            balance = _parse_balance(html)
        if balance is None:
            if any(marker in html for marker in _NOT_LOGGED_IN_MARKERS):
                raise NotLoggedIn(
                    "Cabinet did not log this client in (IP not recognized?)"
                )
            raise ParseError("Баланс row not found on the cabinet page")
        return balance

    async def _async_get_page(self) -> str:
        """Fetch the cabinet page body as text."""
        try:
            async with self._session.get(
                self._url,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
                headers=_HEADERS,
            ) as response:
                response.raise_for_status()
                # The page declares UTF-8; decode explicitly because the
                # server does not always send a charset header.
                return (await response.read()).decode("utf-8", "replace")
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(f"Error fetching {self._url}: {err}") from err

    async def _async_auto_login(self) -> None:
        """Start a session via the plugin's IP-based auto-login endpoint."""
        try:
            async with self._session.post(
                self._login_url,
                data={"auto_login": "1"},
                timeout=aiohttp.ClientTimeout(total=LOGIN_TIMEOUT),
                headers={**_HEADERS, "X-Requested-With": "XMLHttpRequest"},
            ) as response:
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(
                f"Error logging in at {self._login_url}: {err}"
            ) from err
        if not isinstance(payload, dict) or not payload.get("logged"):
            raise NotLoggedIn(f"Auto-login refused at {self._login_url}")
        _LOGGER.debug("Cabinet auto-login OK, retrying %s", self._url)
