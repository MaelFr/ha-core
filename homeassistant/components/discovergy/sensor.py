"""Discovergy sensor entity."""
from dataclasses import dataclass, field
from datetime import timedelta
import logging

from pydiscovergy import Discovergy
from pydiscovergy.error import AccessTokenExpired, HTTPError
from pydiscovergy.models import Meter, Reading

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_IDENTIFIERS,
    ATTR_MANUFACTURER,
    ATTR_MODEL,
    ATTR_NAME,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import DiscovergyData
from .const import (
    CONF_TIME_BETWEEN_UPDATE,
    DEFAULT_TIME_BETWEEN_UPDATE,
    DOMAIN,
    MANUFACTURER,
)

PARALLEL_UPDATES = 1
_LOGGER = logging.getLogger(__name__)


@dataclass
class DiscovergyMixin:
    """Mixin for alternative keys."""

    alternative_keys: list[str] = field(default_factory=lambda: [])
    scale: int = field(default_factory=lambda: 1000)


@dataclass
class DiscovergySensorEntityDescription(DiscovergyMixin, SensorEntityDescription):
    """Define Sensor entity description class."""


GAS_SENSORS: tuple[DiscovergySensorEntityDescription, ...] = (
    DiscovergySensorEntityDescription(
        key="volume",
        translation_key="total_gas_consumption",
        suggested_display_precision=4,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
)

ELECTRICITY_SENSORS: tuple[DiscovergySensorEntityDescription, ...] = (
    # power sensors
    DiscovergySensorEntityDescription(
        key="power",
        translation_key="total_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=3,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    DiscovergySensorEntityDescription(
        key="power1",
        translation_key="phase_1_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=3,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        alternative_keys=["phase1Power"],
    ),
    DiscovergySensorEntityDescription(
        key="power2",
        translation_key="phase_2_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=3,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        alternative_keys=["phase2Power"],
    ),
    DiscovergySensorEntityDescription(
        key="power3",
        translation_key="phase_3_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=3,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        alternative_keys=["phase3Power"],
    ),
    # voltage sensors
    DiscovergySensorEntityDescription(
        key="phase1Voltage",
        translation_key="phase_1_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    DiscovergySensorEntityDescription(
        key="phase2Voltage",
        translation_key="phase_2_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    DiscovergySensorEntityDescription(
        key="phase3Voltage",
        translation_key="phase_3_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # energy sensors
    DiscovergySensorEntityDescription(
        key="energy",
        translation_key="total_consumption",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=4,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        scale=10000000000,
    ),
    DiscovergySensorEntityDescription(
        key="energyOut",
        translation_key="total_production",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=4,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        scale=10000000000,
    ),
)


def get_coordinator_for_meter(
    hass: HomeAssistant,
    meter: Meter,
    discovergy_instance: Discovergy,
    update_interval: timedelta,
) -> DataUpdateCoordinator[Reading]:
    """Create a new DataUpdateCoordinator for given meter."""

    async def async_update_data() -> Reading:
        """Fetch data from API endpoint."""
        try:
            return await discovergy_instance.get_last_reading(meter.get_meter_id())
        except AccessTokenExpired as err:
            raise ConfigEntryAuthFailed(
                "Got token expired while communicating with API"
            ) from err
        except HTTPError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:  # pylint: disable=broad-except
            raise UpdateFailed(
                f"Unexpected error while communicating with API: {err}"
            ) from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sensor",
        update_method=async_update_data,
        update_interval=update_interval,
    )
    return coordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Discovergy sensors."""
    data: DiscovergyData = hass.data[DOMAIN][entry.entry_id]
    discovergy_instance: Discovergy = data.api_client
    meters: list[Meter] = data.meters  # always returns a list

    min_time_between_updates = timedelta(
        seconds=entry.options.get(CONF_TIME_BETWEEN_UPDATE, DEFAULT_TIME_BETWEEN_UPDATE)
    )

    entities: list[DiscovergySensor] = []
    for meter in meters:
        # Get coordinator for meter, set config entry and fetch initial data
        # so we have data when entities are added
        coordinator = get_coordinator_for_meter(
            hass, meter, discovergy_instance, min_time_between_updates
        )
        coordinator.config_entry = entry
        await coordinator.async_config_entry_first_refresh()

        # add coordinator to data for diagnostics
        data.coordinators[meter.get_meter_id()] = coordinator

        sensors = None
        if meter.measurement_type == "ELECTRICITY":
            sensors = ELECTRICITY_SENSORS
        elif meter.measurement_type == "GAS":
            sensors = GAS_SENSORS

        if sensors is not None:
            for description in sensors:
                keys = [description.key] + description.alternative_keys

                # check if this meter has this data, then add this sensor
                for key in keys:
                    if key in coordinator.data.values:
                        entities.append(
                            DiscovergySensor(key, description, meter, coordinator)
                        )

    async_add_entities(entities, False)


class DiscovergySensor(CoordinatorEntity[DataUpdateCoordinator[Reading]], SensorEntity):
    """Represents a discovergy smart meter sensor."""

    entity_description: DiscovergySensorEntityDescription
    data_key: str
    _attr_has_entity_name = True

    def __init__(
        self,
        data_key: str,
        description: DiscovergySensorEntityDescription,
        meter: Meter,
        coordinator: DataUpdateCoordinator[Reading],
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self.data_key = data_key

        self.entity_description = description
        self._attr_unique_id = f"{meter.full_serial_number}-{description.key}"
        self._attr_device_info = {
            ATTR_IDENTIFIERS: {(DOMAIN, meter.get_meter_id())},
            ATTR_NAME: f"{meter.measurement_type.capitalize()} {meter.location.street} {meter.location.street_number}",
            ATTR_MODEL: f"{meter.type} {meter.full_serial_number}",
            ATTR_MANUFACTURER: MANUFACTURER,
        }

    @property
    def native_value(self) -> StateType:
        """Return the sensor state."""
        return float(
            self.coordinator.data.values[self.data_key] / self.entity_description.scale
        )
