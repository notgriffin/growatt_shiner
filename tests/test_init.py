"""Setup/unload tests for the Growatt Shiner integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.growatt_shiner.const import (
    CONF_AI_TASK_ENTITY,
    CONF_REFRESH_TOKEN,
    CONF_SCAN_INTERVAL,
)
from custom_components.growatt_shiner.shiner_api import ShinerAuthError, ShinerError


async def test_setup_and_unload(
    hass: HomeAssistant, mock_shiner, mock_config_entry
) -> None:
    """The entry loads, creates entities, and unloads cleanly."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert len(hass.states.async_entity_ids("sensor")) > 10
    assert hass.states.async_entity_ids("binary_sensor")

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_on_error(
    hass: HomeAssistant, mock_shiner, mock_config_entry
) -> None:
    """A transient API error during first refresh puts the entry in retry."""
    mock_shiner.coordinator.async_get_inverters.side_effect = ShinerError("down")
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_auth_error_triggers_reauth(
    hass: HomeAssistant, mock_shiner, mock_config_entry
) -> None:
    """An auth error during first refresh starts the reauth flow."""
    mock_shiner.coordinator.async_get_inverters.side_effect = ShinerAuthError("expired")
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


async def test_unattended_ai_relogin(
    hass: HomeAssistant, mock_shiner, mock_config_entry, inverter_bundle
) -> None:
    """On session expiry, an AI-solved re-login recovers without a reauth prompt."""
    # First fetch sees an expired session; the retry after re-login succeeds.
    mock_shiner.coordinator.async_get_inverters.side_effect = [
        ShinerAuthError("expired"),
        [inverter_bundle["meta"]],
    ]
    mock_shiner.coordinator.refresh_token = "renewed-token"
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.growatt_shiner.coordinator.async_solve_captcha",
        new=AsyncMock(return_value="1234"),
    ):
        assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    mock_shiner.coordinator.async_login.assert_awaited_once()
    # The freshly minted refresh token is persisted for next time.
    assert mock_config_entry.data[CONF_REFRESH_TOKEN] == "renewed-token"


async def test_options_flow_updates_settings(
    hass: HomeAssistant, mock_shiner, mock_config_entry
) -> None:
    """The options flow stores the scan interval + AI Task entity and reloads."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 120, CONF_AI_TASK_ENTITY: "ai_task.my_assistant"},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_SCAN_INTERVAL] == 120
    assert mock_config_entry.options[CONF_AI_TASK_ENTITY] == "ai_task.my_assistant"
