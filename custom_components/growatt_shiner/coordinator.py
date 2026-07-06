"""DataUpdateCoordinator for the Growatt Shiner integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ai_captcha import async_solve_captcha
from .const import (
    CONF_AI_TASK_ENTITY,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .shiner_api import (
    ShinerApiClient,
    ShinerAuthError,
    ShinerCaptchaError,
    ShinerError,
)

_LOGGER = logging.getLogger(__name__)

# coordinator.data maps an inverter serial -> {"meta", "diagram", "detail"}.
type InverterData = dict[str, dict[str, Any]]


class ShinerCoordinator(DataUpdateCoordinator[InverterData]):
    """Fetch every inverter on the account once per interval."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, session: ClientSession
    ) -> None:
        """Initialize the coordinator from a config entry."""
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )
        self.client = ShinerApiClient(
            session,
            entry.data.get(CONF_HOST, DEFAULT_HOST),
            username=entry.data.get(CONF_USERNAME),
            refresh_token=entry.data.get(CONF_REFRESH_TOKEN),
        )

    async def _async_update_data(self) -> InverterData:
        """Fetch data; on session expiry try an unattended AI re-login first."""
        try:
            return await self._async_fetch()
        except ShinerAuthError as err:
            if await self._async_ai_relogin():
                try:
                    return await self._async_fetch()
                except ShinerError as retry_err:
                    raise UpdateFailed(str(retry_err)) from retry_err
            # No stored password or AI unavailable -> hand off to the reauth flow.
            raise ConfigEntryAuthFailed(str(err)) from err
        except ShinerError as err:
            raise UpdateFailed(str(err)) from err

    async def _async_fetch(self) -> InverterData:
        """Discover inverters, then fetch live diagram + detail for each."""
        inverters = await self.client.async_get_inverters()
        result: InverterData = {}
        for row in inverters:
            serial = row.get("inverter_sn")
            if not serial:
                continue
            diagram = await self.client.async_get_diagram(serial)
            try:
                detail = await self.client.async_get_detail(serial)
            except ShinerError:
                # Detail is optional (temperature/diagnostics); tolerate loss.
                detail = {"by_address": {}, "by_name": {}}
            result[serial] = {"meta": row, "diagram": diagram, "detail": detail}

        if not result:
            raise UpdateFailed("No inverters found on this Growatt Shiner account")
        return result

    async def _async_ai_relogin(self) -> bool:
        """Re-login unattended with the stored password + an AI-solved captcha.

        Returns True if a fresh session was obtained (and the stored refresh
        token updated). Requires a stored password and a working AI Task entity;
        otherwise returns False so the caller falls back to manual reauth.
        """
        entry = self.config_entry
        password = entry.data.get(CONF_PASSWORD)
        username = entry.data.get(CONF_USERNAME)
        if not password or not username:
            return False

        entity_id = entry.options.get(CONF_AI_TASK_ENTITY)
        for _ in range(3):  # captchas are cheap to retry if the AI misreads
            try:
                image = await self.client.async_prepare_login()
            except ShinerError:
                return False
            code = await async_solve_captcha(self.hass, image, entity_id)
            if not code:
                return False
            try:
                await self.client.async_login(username, password, code)
            except ShinerCaptchaError:
                continue
            except ShinerError:
                return False
            self.hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_REFRESH_TOKEN: self.client.refresh_token},
            )
            _LOGGER.info("Growatt Shiner session renewed automatically via AI captcha")
            return True
        return False
