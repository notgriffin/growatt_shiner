"""Diagnostics support for the Growatt Shiner integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ShinerConfigEntry
from .const import CONF_PASSWORD, CONF_REFRESH_TOKEN, CONF_USER_ID, CONF_USERNAME

TO_REDACT = {
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
    CONF_USER_ID,
    "password",
    "username",
    "user_id",
    "email",
    "gateway",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ShinerConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "data": async_redact_data(coordinator.data or {}, TO_REDACT),
    }
