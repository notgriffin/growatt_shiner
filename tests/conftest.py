"""Shared fixtures for the Growatt Shiner test suite."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.growatt_shiner.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
)

SERIAL = "SMN0T0000R"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components/ in every test (provided by PHACC)."""
    yield


@pytest.fixture
def inverter_bundle() -> dict:
    """One inverter's {meta, diagram, detail} bundle, as the coordinator builds."""
    return {
        "meta": {
            "inverter_sn": SERIAL,
            "model": "MIN 8.2-11.4KTL-XH-US",
            "version": "2.0.1.3",
            "is_online": 1,
            "plant": {"name": "Test Plant"},
            "alias": "",
        },
        "diagram": {
            "is_online": 1,
            "pvPower": 5000.0,
            "pac": 4000.0,
            "loadPower": 4000.0,
            "pv1Voltage": 200.0,
            "pv1Power": 1000.0,
            "phaseRVoltage": 240.0,
            "gridFreq": 60.00,
            "powerFactor": 0.99,
            "socBdc1": 0,
            "chargePower": 0,
            "v2TodayProduction": 25.0,
            "v2TotalProduction": 150,
            "v2TodayConsumption": 25.0,
        },
        "detail": {"by_address": {73093: 42.0, 73098: 375.0, 6: 11400}, "by_name": {}},
    }


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A config entry as the config flow would create it."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Growatt Shiner (test-user)",
        data={
            CONF_USERNAME: "test-user",
            CONF_PASSWORD: "test-password",
            CONF_HOST: "https://shiner-us.growatt.com",
            CONF_REFRESH_TOKEN: "stored-refresh-token",
            CONF_USER_ID: 123456,
        },
        unique_id="123456",
    )


def _configure_client(client: MagicMock, bundle: dict) -> None:
    client.async_get_inverters = AsyncMock(return_value=[bundle["meta"]])
    client.async_get_diagram = AsyncMock(return_value=bundle["diagram"])
    client.async_get_detail = AsyncMock(return_value=bundle["detail"])
    client.async_prepare_login = AsyncMock(return_value="data:image/png;base64,AAAA")
    client.async_login = AsyncMock(
        return_value={"id": 123456, "username": "test-user"}
    )
    client.refresh_token = "test-refresh-token"


@pytest.fixture
def mock_shiner(inverter_bundle):
    """Patch the client (in coordinator + config_flow) and the aiohttp sessions."""
    session = MagicMock()
    session.close = AsyncMock()
    with (
        patch(
            "custom_components.growatt_shiner.coordinator.ShinerApiClient",
            autospec=True,
        ) as coord_cls,
        patch(
            "custom_components.growatt_shiner.config_flow.ShinerApiClient",
            autospec=True,
        ) as flow_cls,
        patch(
            "custom_components.growatt_shiner.async_create_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.growatt_shiner.config_flow.async_create_clientsession",
            return_value=session,
        ),
    ):
        _configure_client(coord_cls.return_value, inverter_bundle)
        _configure_client(flow_cls.return_value, inverter_bundle)
        yield SimpleNamespace(
            coordinator=coord_cls.return_value, flow=flow_cls.return_value
        )
