"""The Growatt Shiner integration."""

from __future__ import annotations

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import PLATFORMS
from .coordinator import ShinerCoordinator

type ShinerConfigEntry = ConfigEntry[ShinerCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ShinerConfigEntry) -> bool:
    """Set up Growatt Shiner from a config entry."""
    # Dedicated session with no cookie jar: the client manages the Shiner auth
    # cookies explicitly, and this keeps multiple accounts fully isolated.
    session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())

    async def _close_session() -> None:
        await session.close()

    entry.async_on_unload(_close_session)

    coordinator = ShinerCoordinator(hass, entry, session)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ShinerConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ShinerConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
