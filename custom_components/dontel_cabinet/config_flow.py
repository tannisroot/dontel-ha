"""Config flow for the ДонТел Личный кабинет integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .client import (
    CannotConnect,
    DontelCabinetClient,
    DontelCabinetError,
    NotLoggedIn,
    async_create_cabinet_session,
    normalize_cabinet_url,
)
from .const import DEFAULT_TIMEOUT, DEFAULT_URL, DOMAIN

STEP_URL_SCHEMA = vol.Schema({vol.Required("url", default=DEFAULT_URL): cv.string})


async def _try_cabinet(hass: HomeAssistant, url: str) -> float:
    """Return the balance for `url`; raises DontelCabinetError on any problem."""
    # Patched in tests to capture the flow session on a virtual transport.
    session = async_create_cabinet_session(hass)
    client = DontelCabinetClient(session, url, DEFAULT_TIMEOUT)
    try:
        return await client.async_get_balance()
    finally:
        # One-off session for the flow; HA keeps the shared connector open.
        session.detach()


class DontelCabinetConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the ДонТел cabinet.

    The integration identifies the cabinet by host and the cabinet
    identifies the subscriber by client IP, so exactly one entry makes sense.
    """

    VERSION = 1

    _reauth_url: str

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: the cabinet URL."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                url = normalize_cabinet_url(user_input["url"])
            except ValueError:
                errors["base"] = "invalid_url"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured(updates={"url": url})
                try:
                    await _try_cabinet(self.hass, url)
                except NotLoggedIn:
                    errors["base"] = "not_logged_in"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except DontelCabinetError:
                    errors["base"] = "parse_error"
                else:
                    return self.async_create_entry(
                        title="ДонТел Личный кабинет",
                        data={"url": url},
                    )

        return self.async_show_form(
            step_id="user", data_schema=STEP_URL_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Prompt the user when the cabinet stops recognizing our IP."""
        self._reauth_url = entry_data["url"]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Retry the auto-login after the user confirms."""
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                await _try_cabinet(self.hass, self._reauth_url)
            except NotLoggedIn:
                return self.async_show_form(
                    step_id="reauth_confirm",
                    description_placeholders={"url": self._reauth_url},
                    errors={"base": "not_logged_in"},
                )
            except CannotConnect:
                return self.async_show_form(
                    step_id="reauth_confirm",
                    description_placeholders={"url": self._reauth_url},
                    errors={"base": "cannot_connect"},
                )
            except DontelCabinetError:
                return self.async_show_form(
                    step_id="reauth_confirm",
                    description_placeholders={"url": self._reauth_url},
                    errors={"base": "parse_error"},
                )
            return self.async_update_reload_and_abort(entry)

        return self.async_show_form(
            step_id="reauth_confirm",
            description_placeholders={"url": self._reauth_url},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing the cabinet URL."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                url = normalize_cabinet_url(user_input["url"])
            except ValueError:
                errors["base"] = "invalid_url"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_mismatch(reason="unique_id_mismatch")
                try:
                    await _try_cabinet(self.hass, url)
                except NotLoggedIn:
                    errors["base"] = "not_logged_in"
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                except DontelCabinetError:
                    errors["base"] = "parse_error"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={"url": url},
                        reload_even_if_entry_is_unchanged=False,
                    )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {vol.Required("url", default=entry.data["url"]): cv.string}
            ),
            errors=errors,
        )
