"""Sensor/binary-sensor state tests for the Growatt Shiner integration."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.growatt_shiner.const import DOMAIN

SERIAL = "SMN0T0000R"


@pytest.fixture
async def setup_integration(hass: HomeAssistant, mock_shiner, mock_config_entry):
    """Set the entry up and return the entity registry."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return er.async_get(hass)


def _state(hass: HomeAssistant, ent_reg, unique_id: str):
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id, f"no sensor for {unique_id}"
    return hass.states.get(entity_id)


@pytest.mark.parametrize(
    ("unique_id", "expected"),
    [
        (f"{SERIAL}_pv_power", "5000.0"),
        (f"{SERIAL}_ac_power", "4000.0"),
        (f"{SERIAL}_load_power", "4000.0"),
        (f"{SERIAL}_battery_soc", "0"),
        (f"{SERIAL}_production_today", "25.0"),
        (f"{SERIAL}_production_total", "150"),
        (f"{SERIAL}_consumption_today", "25.0"),
        (f"{SERIAL}_inverter_temperature", "42.0"),
    ],
)
async def test_sensor_values(
    hass: HomeAssistant, setup_integration, unique_id, expected
) -> None:
    """Enabled sensors read their mapped value from the diagram/detail bundle."""
    assert _state(hass, setup_integration, unique_id).state == expected


async def test_diagnostic_sensor_disabled_by_default(
    hass: HomeAssistant, setup_integration
) -> None:
    """Voltage/current/frequency diagnostics register but are off by default."""
    ent_reg = setup_integration
    entity_id = ent_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{SERIAL}_grid_frequency"
    )
    assert entity_id
    assert ent_reg.async_get(entity_id).disabled_by is not None


async def test_device_and_units(hass: HomeAssistant, setup_integration) -> None:
    """PV power carries the right unit and belongs to the inverter device."""
    ent_reg = setup_integration
    entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_pv_power")
    state = hass.states.get(entity_id)
    assert state.attributes["unit_of_measurement"] == "W"
    assert state.attributes["device_class"] == "power"


async def test_online_binary_sensor(hass: HomeAssistant, setup_integration) -> None:
    """The connectivity binary sensor is on when the inverter is online."""
    ent_reg = setup_integration
    entity_id = ent_reg.async_get_entity_id("binary_sensor", DOMAIN, f"{SERIAL}_online")
    assert entity_id
    assert hass.states.get(entity_id).state == "on"
