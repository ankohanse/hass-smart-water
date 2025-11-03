import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

import homeassistant.helpers.entity_registry as entity_registry

from .const import (
    PLATFORMS,
    BINARY_SENSOR_VALUES_ALL,
)
from .coordinator import (
    SmartWaterCoordinatorFactory,
    SmartWaterCoordinator
)
from custom_components.smartwater.data import (
    SmartWaterData,
)


_LOGGER = logging.getLogger(__name__)


class SmartWaterEntityHelperFactory:

    @staticmethod
    def create(hass: HomeAssistant, config_entry: ConfigEntry):
        """
        Get entity helper for a config entry.
        The entry is short lived (only during init) and does not contain state data,
        therefore no need to cache it in hass.data
        """

        # Get an instance of the SmartWaterCoordinator for this install_id
        coordinator = SmartWaterCoordinatorFactory.create(hass, config_entry)

        # Get an instance of our helper
        return SmartWaterEntityHelper(hass, coordinator)


class SmartWaterEntityHelper:
    """My custom helper to provide common functions."""

    def __init__(self, hass: HomeAssistant, coordinator: SmartWaterCoordinator):
        self._coordinator = coordinator
        self._entity_registry = entity_registry.async_get(hass)


    async def async_setup_entry(self, target_platform: Platform, target_class: type, async_add_entities: AddEntitiesCallback):
        """
        Setting up the adding and updating of sensor and binary_sensor entities
        """
        # Get data from the coordinator
        devices:dict[str,SmartWaterData] = self._coordinator.data

        if not devices:
            # If data returns False or is empty, log an error and return
            _LOGGER.warning(f"Failed to fetch entity data - authentication failed or no data.")
            return

        _LOGGER.debug(f"Create {target_platform} entities for profile '{self._coordinator.profile_name}'")

        # Iterate all statuses to create sensor entities
        entities = []
        valid_unique_ids: list[str] = []

        for device in devices.values():
            for datapoint in device.get_datapoints_for_platform(target_platform):

                # Create a Sensor, Binary_Sensor, Number, Select, Switch or other entity for this datapoint
                entity = None
                try:
                    entity = target_class(self._coordinator, device, datapoint.key)
                    entities.append(entity)

                    valid_unique_ids.append(entity.unique_id)

                except Exception as  ex:
                    _LOGGER.warning(f"Could not instantiate {target_platform} entity class for {device.id}:{datapoint.key}. Details: {ex}")

        # Remember valid unique_ids per platform so we can do an entity cleanup later
        self._coordinator.set_valid_unique_ids(target_platform, valid_unique_ids)

        # Now add the entities to the entity_registry
        _LOGGER.info(f"Add {len(entities)} {target_platform} entities for profile '{self._coordinator.profile_name}'")
        if entities:
            async_add_entities(entities)


