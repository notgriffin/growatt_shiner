"""Config-flow tests for the Growatt Shiner integration."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.growatt_shiner.const import (
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.growatt_shiner.shiner_api import (
    ShinerAuthError,
    ShinerCaptchaError,
    ShinerError,
)

USER_INPUT = {
    "username": "test-user",
    "password": "secret",
    "host": "United States",
}
CAPTCHA_INPUT = {"captcha": "1234"}


async def _to_captcha(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    return result


async def test_full_flow(hass: HomeAssistant, mock_shiner) -> None:
    """User step -> captcha step -> entry created with the refresh token."""
    result = await _to_captcha(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "captcha"
    # The captcha image is passed to the frontend for rendering.
    assert result["description_placeholders"]["captcha_image"].startswith("data:image")

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CAPTCHA_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "123456"
    assert result["data"][CONF_USERNAME] == "test-user"
    assert result["data"][CONF_REFRESH_TOKEN] == "test-refresh-token"
    # Password is stored so unattended re-authentication can log in again.
    assert result["data"][CONF_PASSWORD] == "secret"


async def test_cannot_connect(hass: HomeAssistant, mock_shiner) -> None:
    """A connection error on the user step shows cannot_connect."""
    mock_shiner.flow.async_prepare_login.side_effect = ShinerError("boom")
    result = await _to_captcha(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_invalid_captcha(hass: HomeAssistant, mock_shiner) -> None:
    """A wrong captcha re-shows the captcha step with an error."""
    mock_shiner.flow.async_login.side_effect = ShinerCaptchaError("nope")
    result = await _to_captcha(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CAPTCHA_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "captcha"
    assert result["errors"] == {"base": "invalid_captcha"}


async def test_invalid_auth(hass: HomeAssistant, mock_shiner) -> None:
    """Bad credentials show invalid_auth."""
    mock_shiner.flow.async_login.side_effect = ShinerAuthError("bad creds")
    result = await _to_captcha(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CAPTCHA_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "captcha"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_duplicate_aborts(
    hass: HomeAssistant, mock_shiner, mock_config_entry
) -> None:
    """Re-adding the same account (unique_id) aborts as already_configured."""
    mock_config_entry.add_to_hass(hass)
    result = await _to_captcha(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CAPTCHA_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow(hass: HomeAssistant, mock_shiner, mock_config_entry) -> None:
    """Reauth re-prompts for password + captcha and updates the refresh token."""
    mock_config_entry.add_to_hass(hass)
    mock_shiner.flow.refresh_token = "new-refresh-token"

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "newsecret"}
    )
    assert result["step_id"] == "captcha"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], CAPTCHA_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_REFRESH_TOKEN] == "new-refresh-token"
