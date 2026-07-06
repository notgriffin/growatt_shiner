"""Binary sensor platform for the Growatt Shiner integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShinerConfigEntry
from .coordinator import ShinerCoordinator
from .entity import ShinerInverterEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShinerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up an online/connectivity binary sensor per inverter."""
    coordinator = entry.runtime_data
    async_add_entities(
        ShinerOnlineBinarySensor(coordinator, serial) for serial in coordinator.data
    )


class ShinerOnlineBinarySensor(ShinerInverterEntity, BinarySensorEntity):
    """On while the inverter is reporting to the Growatt cloud."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "online"

    def __init__(self, coordinator: ShinerCoordinator, serial: str) -> None:
        """Initialize the connectivity binary sensor."""
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_online"

    @property
    def is_on(self) -> bool:
        """Return True if the inverter is online."""
        diagram = self._inverter.get("diagram") or {}
        meta = self._inverter.get("meta") or {}
        return bool(diagram.get("is_online") or meta.get("is_online"))
