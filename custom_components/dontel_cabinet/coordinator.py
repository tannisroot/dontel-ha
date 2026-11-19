"""Data update coordinator for the ДонТел cabinet balance."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import (
    DontelCabinetClient,
    DontelCabinetError,
    NotLoggedIn,
    ParseError,
)
from .const import DEFAULT_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__package__)


class DontelBalanceCoordinator(DataUpdateCoordinator[float]):
    """Poll the cabinet page once per hour."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: DontelCabinetClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="ДонТел cabinet balance",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> float:
        """Fetch the balance from the cabinet page."""
        try:
            balance = await self.client.async_get_balance()
        except NotLoggedIn as err:
            # The cabinet stopped recognizing us; the user has to notice.
            raise ConfigEntryAuthFailed(
                translation_domain="dontel_cabinet",
                translation_key="not_logged_in",
            ) from err
        except ParseError as err:
            raise UpdateFailed(
                translation_domain="dontel_cabinet",
                translation_key="parse_error",
            ) from err
        except DontelCabinetError as err:
            raise UpdateFailed(
                translation_domain="dontel_cabinet",
                translation_key="cannot_connect",
            ) from err
        _LOGGER.debug("Cabinet balance updated: %s", balance)
        return balance
