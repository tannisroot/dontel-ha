"""Sensor platform for the ДонТел Личный кабинет integration."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DontelConfigEntry
from .const import CURRENCY, DOMAIN
from .coordinator import DontelBalanceCoordinator


class DontelBalanceSensor(CoordinatorEntity[DontelBalanceCoordinator], SensorEntity):
    """Account balance (Баланс) from the ISP cabinet."""

    _attr_has_entity_name = True
    _attr_translation_key = "balance"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = CURRENCY
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: DontelBalanceCoordinator,
        unique_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unique_id)},
            name="ДонТел Личный кабинет",
            manufacturer="Донтел",
            model="Личный кабинет",
        )

    @property
    def native_value(self) -> float | None:
        """Return the latest balance."""
        return self.coordinator.data

    @property
    def available(self) -> bool:
        """Keep the last good balance while the cabinet is merely unreachable.

        A slow or failing cabinet page must not turn the bill balance into
        `unavailable` for an hour. When the cabinet stopped recognizing our
        IP (reauth pending), however, the value is no longer trustworthy and
        the entity goes unavailable to surface the problem.
        """
        if self.coordinator.last_update_success:
            return True
        if isinstance(self.coordinator.last_exception, ConfigEntryAuthFailed):
            return False
        return self.coordinator.data is not None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DontelConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the balance sensor from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities([DontelBalanceSensor(coordinator, entry.unique_id)])
