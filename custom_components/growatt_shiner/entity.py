"""Base entity for the Growatt Shiner integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ShinerCoordinator


class ShinerInverterEntity(CoordinatorEntity[ShinerCoordinator]):
    """Shared base for entities belonging to one inverter (by serial)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ShinerCoordinator, serial: str) -> None:
        """Initialize and attach per-inverter device info."""
        super().__init__(coordinator)
        self._serial = serial
        meta = coordinator.data[serial].get("meta", {})
        plant = meta.get("plant") or meta.get("site") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="Growatt",
            model=meta.get("model") or "Shiner inverter",
            name=meta.get("alias") or plant.get("name") or f"Growatt {serial}",
            serial_number=serial,
            sw_version=meta.get("version"),
        )

    @property
    def _inverter(self) -> dict[str, Any]:
        """Return this inverter's ``{meta, diagram, detail}`` bundle."""
        return self.coordinator.data.get(self._serial, {})

    @property
    def available(self) -> bool:
        """Available while the coordinator succeeds and the inverter is present."""
        return super().available and self._serial in self.coordinator.data
