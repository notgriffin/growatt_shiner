"""Sensor platform for the Growatt Shiner integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ShinerConfigEntry
from .coordinator import ShinerCoordinator
from .entity import ShinerInverterEntity

# Modbus register addresses for values only exposed in the "detail" tree.
_REG_INVERTER_TEMP = 73093
_REG_P_BUS_VOLTAGE = 73098
_REG_RATED_POWER = 6


@dataclass(frozen=True, kw_only=True)
class ShinerSensorDescription(SensorEntityDescription):
    """Describes a Growatt Shiner sensor and how to read its value."""

    # ``data`` is one inverter's {"meta", "diagram", "detail"} bundle.
    value_fn: Callable[[dict[str, Any]], float | int | str | None]


def _diag(key: str) -> Callable[[dict[str, Any]], Any]:
    """Read a field from the inverter's live diagram."""
    return lambda data: (data.get("diagram") or {}).get(key)


def _reg(address: int) -> Callable[[dict[str, Any]], Any]:
    """Read a value from the inverter detail tree by Modbus register address."""
    return lambda data: (data.get("detail") or {}).get("by_address", {}).get(address)


def _power(key: str, name: str, src: Callable) -> ShinerSensorDescription:
    return ShinerSensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=src,
    )


def _energy(key: str, name: str, src: Callable) -> ShinerSensorDescription:
    return ShinerSensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value_fn=src,
    )


def _voltage(key: str, name: str, src: Callable) -> ShinerSensorDescription:
    return ShinerSensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=src,
    )


def _current(key: str, name: str, src: Callable) -> ShinerSensorDescription:
    return ShinerSensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=src,
    )


def _battery(key: str, name: str, src: Callable) -> ShinerSensorDescription:
    return ShinerSensorDescription(
        key=key,
        name=name,
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=src,
    )


SENSORS: tuple[ShinerSensorDescription, ...] = (
    # Live power
    _power("pv_power", "PV power", _diag("pvPower")),
    _power("ac_power", "AC output power", _diag("pac")),
    _power("output_power", "Inverter output power", _diag("invOutPower")),
    _power("load_power", "Load power", _diag("loadPower")),
    _power("power_to_grid", "Power to grid", _diag("powerToGrid")),
    _power("power_to_user", "Power from grid", _diag("powerToUser")),
    _power("battery_charge_power", "Battery charge power", _diag("chargePower")),
    _power(
        "battery_discharge_power", "Battery discharge power", _diag("dischargePower")
    ),
    _power("generator_power", "Generator power", _diag("generatorPower")),
    # PV strings
    _power("pv1_power", "PV1 power", _diag("pv1Power")),
    _power("pv2_power", "PV2 power", _diag("pv2Power")),
    _power("pv3_power", "PV3 power", _diag("pv3Power")),
    _power("pv4_power", "PV4 power", _diag("pv4Power")),
    _voltage("pv1_voltage", "PV1 voltage", _diag("pv1Voltage")),
    _voltage("pv2_voltage", "PV2 voltage", _diag("pv2Voltage")),
    _voltage("pv3_voltage", "PV3 voltage", _diag("pv3Voltage")),
    _voltage("pv4_voltage", "PV4 voltage", _diag("pv4Voltage")),
    _current("pv1_current", "PV1 current", _diag("pv1Current")),
    _current("pv2_current", "PV2 current", _diag("pv2Current")),
    _current("pv3_current", "PV3 current", _diag("pv3Current")),
    _current("pv4_current", "PV4 current", _diag("pv4Current")),
    # Grid
    _voltage("grid_voltage", "Grid voltage", _diag("phaseRVoltage")),
    _current("grid_current", "Grid current", _diag("phaseRCurrent")),
    ShinerSensorDescription(
        key="grid_frequency",
        name="Grid frequency",
        device_class=SensorDeviceClass.FREQUENCY,
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=_diag("gridFreq"),
    ),
    ShinerSensorDescription(
        key="power_factor",
        name="Power factor",
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        entity_registry_enabled_default=False,
        value_fn=_diag("powerFactor"),
    ),
    # Battery
    _battery("battery_soc", "Battery SOC", _diag("socBdc1")),
    _battery("battery_soc_2", "Battery SOC 2", _diag("socBdc2")),
    # Energy today
    _energy("production_today", "Production today", _diag("v2TodayProduction")),
    _energy("consumption_today", "Consumption today", _diag("v2TodayConsumption")),
    _energy(
        "energy_from_solar_today", "Energy from solar today", _diag("etodayFromSolar")
    ),
    _energy("energy_to_grid_today", "Energy to grid today", _diag("etodayToGrid")),
    _energy(
        "energy_from_grid_today", "Energy from grid today", _diag("etodayFromGrid")
    ),
    _energy("energy_to_load_today", "Energy to load today", _diag("etodayToLoad")),
    _energy("battery_charged_today", "Battery charged today", _diag("etodayToBattery")),
    _energy(
        "battery_discharged_today",
        "Battery discharged today",
        _diag("etodayFromBattery"),
    ),
    # Energy total
    _energy("production_total", "Production total", _diag("v2TotalProduction")),
    _energy("consumption_total", "Consumption total", _diag("v2TotalConsumption")),
    _energy(
        "energy_from_solar_total", "Energy from solar total", _diag("etotalFromSolar")
    ),
    _energy("energy_to_grid_total", "Energy to grid total", _diag("etotalToGrid")),
    _energy(
        "energy_from_grid_total", "Energy from grid total", _diag("etotalFromGrid")
    ),
    _energy("energy_to_load_total", "Energy to load total", _diag("etotalToLoad")),
    _energy("battery_charged_total", "Battery charged total", _diag("etotalToBattery")),
    _energy(
        "battery_discharged_total",
        "Battery discharged total",
        _diag("etotalFromBattery"),
    ),
    _energy("system_energy_total", "System energy total", _diag("etotalSystem")),
    # Diagnostics (from the detail tree, by Modbus register)
    ShinerSensorDescription(
        key="inverter_temperature",
        name="Inverter temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_reg(_REG_INVERTER_TEMP),
    ),
    _voltage("p_bus_voltage", "P bus voltage", _reg(_REG_P_BUS_VOLTAGE)),
    ShinerSensorDescription(
        key="rated_power",
        name="Rated power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_reg(_REG_RATED_POWER),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ShinerConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform: one set of sensors per inverter."""
    coordinator = entry.runtime_data
    async_add_entities(
        ShinerSensor(coordinator, serial, description)
        for serial in coordinator.data
        for description in SENSORS
    )


class ShinerSensor(ShinerInverterEntity, SensorEntity):
    """A single Growatt Shiner sensor for one inverter."""

    entity_description: ShinerSensorDescription

    def __init__(
        self,
        coordinator: ShinerCoordinator,
        serial: str,
        description: ShinerSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, serial)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"

    @property
    def native_value(self) -> float | int | str | None:
        """Return the current value."""
        return self.entity_description.value_fn(self._inverter)
