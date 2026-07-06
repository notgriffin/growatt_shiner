"""Config flow for the Growatt Shiner integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    CONF_AI_TASK_ENTITY,
    CONF_CAPTCHA,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
    CONF_USER_ID,
    CONF_USERNAME,
    DEFAULT_HOST,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    HOSTS,
    MIN_SCAN_INTERVAL,
)
from .shiner_api import (
    ShinerApiClient,
    ShinerAuthError,
    ShinerCaptchaError,
    ShinerError,
)

_AI_TASK_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="ai_task")
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_HOST, default=next(iter(HOSTS))): vol.In(list(HOSTS)),
        vol.Optional(CONF_AI_TASK_ENTITY): _AI_TASK_SELECTOR,
    }
)
STEP_CAPTCHA_SCHEMA = vol.Schema({vol.Required(CONF_CAPTCHA): str})


class ShinerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup flow for Growatt Shiner."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize per-flow state."""
        self._client: ShinerApiClient | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._host: str = DEFAULT_HOST
        self._ai_task_entity: str | None = None
        self._captcha_image: str | None = None
        self._reauth: bool = False

    async def _async_prepare(self) -> None:
        """Start a fresh login handshake and fetch a captcha."""
        session = async_create_clientsession(
            self.hass, cookie_jar=aiohttp.DummyCookieJar()
        )
        self._client = ShinerApiClient(session, self._host, username=self._username)
        self._captcha_image = await self._client.async_prepare_login()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect credentials + region, then fetch a captcha."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            self._host = HOSTS.get(user_input[CONF_HOST], DEFAULT_HOST)
            self._ai_task_entity = user_input.get(CONF_AI_TASK_ENTITY)
            try:
                await self._async_prepare()
            except ShinerError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_captcha()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the captcha image and complete login."""
        assert self._client is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                user = await self._client.async_login(
                    self._username, self._password, user_input[CONF_CAPTCHA]
                )
            except ShinerCaptchaError:
                errors["base"] = "invalid_captcha"
                await self._async_prepare()  # captcha is single-use; fetch a new one
            except ShinerAuthError:
                errors["base"] = "invalid_auth"
                await self._async_prepare()
            except ShinerError:
                errors["base"] = "cannot_connect"
                await self._async_prepare()
            else:
                return await self._async_finish(user)

        return self.async_show_form(
            step_id="captcha",
            data_schema=STEP_CAPTCHA_SCHEMA,
            errors=errors,
            description_placeholders={"captcha_image": self._captcha_image or ""},
        )

    async def _async_finish(self, user: dict[str, Any]) -> ConfigFlowResult:
        """Create or update the config entry from a successful login."""
        assert self._client is not None
        data = {
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_HOST: self._host,
            CONF_REFRESH_TOKEN: self._client.refresh_token,
            CONF_USER_ID: user.get("id"),
        }

        if self._reauth:
            # Keep existing options (AI entity, scan interval); refresh creds.
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data=data
            )

        await self.async_set_unique_id(str(user.get("id")))
        self._abort_if_unique_id_configured()
        options = {}
        if self._ai_task_entity:
            options[CONF_AI_TASK_ENTITY] = self._ai_task_entity
        title = user.get("username") or self._username
        return self.async_create_entry(
            title=f"Growatt Shiner ({title})", data=data, options=options
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the refresh token expires."""
        self._reauth = True
        self._username = entry_data.get(CONF_USERNAME)
        self._host = entry_data.get(CONF_HOST, DEFAULT_HOST)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-enter the password, then run the captcha login again."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._password = user_input[CONF_PASSWORD]
            try:
                await self._async_prepare()
            except ShinerError:
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_captcha()

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"username": self._username or ""},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> ShinerOptionsFlow:
        """Return the options flow."""
        return ShinerOptionsFlow()


class ShinerOptionsFlow(OptionsFlow):
    """Scan interval + AI Task entity for unattended captcha solving."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            # An empty AI Task entity selection clears the option.
            data = {k: v for k, v in user_input.items() if v not in (None, "")}
            return self.async_create_entry(title="", data=data)

        options = self.config_entry.options
        current_ai = options.get(CONF_AI_TASK_ENTITY)
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                vol.Optional(
                    CONF_AI_TASK_ENTITY,
                    description={"suggested_value": current_ai},
                ): _AI_TASK_SELECTOR,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
