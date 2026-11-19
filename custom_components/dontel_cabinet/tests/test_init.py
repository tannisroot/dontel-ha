"""End-to-end tests against a fake carbon-billing cabinet."""

from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator

import pytest
from aiohttp import web
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.dontel_cabinet.const import DOMAIN

from .conftest import AUTHED_PAGE, LOGIN_PAGE

CABINET_PATH = "/cabinet/welcome/"
LOGIN_PATH = "/wp-content/plugins/carbon-billing/ajax_login.php"


class FakeCabinet:
    """Stand-in for the ISP cabinet: IP auto-login + cookie sessions.

    `ip_allowed` flips the client's "home IP": existing sessions stop being
    honored and auto-login is refused, like the real server on a new address.
    """

    def __init__(self) -> None:
        self.ip_allowed = True
        self.page = AUTHED_PAGE
        self.sessions: set[str] = set()
        self.login_calls = 0
        self.port = 0

    async def page_handler(self, request: web.Request) -> web.Response:
        cookie = request.cookies.get("PHPSESSID")
        if not self.ip_allowed or cookie not in self.sessions:
            return web.Response(text=LOGIN_PAGE, content_type="text/html")
        return web.Response(text=self.page, content_type="text/html")

    async def login_handler(self, request: web.Request) -> web.Response:
        self.login_calls += 1
        if not self.ip_allowed:
            return web.json_response({"logged": False})
        session_id = secrets.token_hex(16)
        self.sessions.add(session_id)
        resp = web.json_response({"logged": True})
        resp.set_cookie("PHPSESSID", session_id, path="/")
        return resp


@pytest.fixture
async def cabinet() -> AsyncGenerator[FakeCabinet, None]:
    """Run the fake cabinet on a random localhost port."""
    fake = FakeCabinet()
    app = web.Application()
    app.router.add_get(CABINET_PATH, fake.page_handler)
    app.router.add_get(CABINET_PATH.rstrip("/"), fake.page_handler)
    app.router.add_post(LOGIN_PATH, fake.login_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    fake.port = runner.addresses[0][1]
    yield fake
    await runner.cleanup()


def cabinet_url(fake: FakeCabinet) -> str:
    return f"http://127.0.0.1:{fake.port}{CABINET_PATH}"


async def _create_entry(hass: HomeAssistant, url: str):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": url}
    )
    await hass.async_block_till_done()
    return result


async def test_config_flow_creates_entry(
    hass: HomeAssistant, cabinet: FakeCabinet
) -> None:
    """The user step logs in via the cookie session and stores the URL."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": cabinet_url(cabinet)}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"url": cabinet_url(cabinet)}
    await hass.async_block_till_done()
    assert result["result"].state is ConfigEntryState.LOADED
    # One unauthenticated page -> auto-login -> authed page per session
    # (one session in the flow, a fresh one in entry setup).
    assert cabinet.login_calls == 2


async def test_sensor_shows_balance(hass: HomeAssistant, cabinet: FakeCabinet) -> None:
    """The sensor exposes Баланс 2 589,09 as 2589.09 RUB."""
    result = await _create_entry(hass, cabinet_url(cabinet))
    assert result["type"] is FlowResultType.CREATE_ENTRY

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, DOMAIN)
    assert entity_id is not None

    state = hass.states.get(entity_id)
    assert state is not None
    assert float(state.state) == pytest.approx(2589.09)
    assert state.attributes["unit_of_measurement"] == "RUB"
    assert state.attributes["device_class"] == SensorDeviceClass.MONETARY
    assert state.attributes["state_class"] == SensorStateClass.TOTAL


async def test_config_flow_cannot_connect(hass: HomeAssistant) -> None:
    """A dead address surfaces as cannot_connect."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": "http://127.0.0.1:1/cabinet/welcome/"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_invalid_url(hass: HomeAssistant) -> None:
    """Garbage addresses are rejected without a request."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": "не адрес"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_url"}


async def test_config_flow_not_logged_in(
    hass: HomeAssistant, cabinet: FakeCabinet
) -> None:
    """When auto-login is refused the user sees not_logged_in and can retry."""
    cabinet.ip_allowed = False
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": cabinet_url(cabinet)}
    )
    assert result["errors"] == {"base": "not_logged_in"}

    cabinet.ip_allowed = True
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"url": cabinet_url(cabinet)}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_reauth_flow(hass: HomeAssistant, cabinet: FakeCabinet) -> None:
    """A changed IP marks the entry for reauth; confirming fixes it."""
    result = await _create_entry(hass, cabinet_url(cabinet))
    entry = result["result"]

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, DOMAIN)
    assert entity_id is not None

    # IP changed: sessions die and the auto-login is refused.
    cabinet.ip_allowed = False
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # While reauth is pending the stale value is not trustworthy.
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_REAUTH

    # Retrying while the IP is still wrong shows the error.
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], user_input={}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "not_logged_in"}

    cabinet.ip_allowed = True
    result = await hass.config_entries.flow.async_configure(
        flows[0]["flow_id"], user_input={}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(2589.09)


async def test_parse_failure_keeps_last_value(
    hass: HomeAssistant, cabinet: FakeCabinet
) -> None:
    """A page without the Баланс row does not wipe the last good balance."""
    result = await _create_entry(hass, cabinet_url(cabinet))
    entry = result["result"]

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, DOMAIN)
    assert hass.states.get(entity_id).state == "2589.09"

    # Site redesign: the logged-in page no longer carries the row.
    cabinet.page = "<html><body>новая версия кабинета</body></html>"
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # Coordinator failed, but the entity deliberately keeps the last balance.
    assert coordinator.last_update_success is False
    state = hass.states.get(entity_id)
    assert float(state.state) == pytest.approx(2589.09)
