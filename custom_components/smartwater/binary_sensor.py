import asyncio
import logging
import math
from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant import exceptions
from homeassistant.components.binary_sensor import PLATFORM_SCHEMA as PARENT_PLATFORM_SCHEMA
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.binary_sensor import ENTITY_ID_FORMAT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.const import EntityCategory
from homeassistant.const import Platform
from homeassistant.const import STATE_ON
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from datetime import datetime
from datetime import timezone
from datetime import timedelta

from collections import defaultdict
from collections import namedtuple

from .const import (
    DOMAIN,
    BINARY_SENSOR_VALUES_ON,
    BINARY_SENSOR_VALUES_OFF,
    STATUS_VALIDITY_PERIOD,
    utcnow,
)
from .coordinator import (
    SmartWaterCoordinator,
)
from .data import (
    SmartWaterData,
)
from .entity_base import (
    SmartWaterEntity,
)
from .entity_helper import (
    SmartWaterEntityHelper,
)


_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PARENT_PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of binary_sensor entities
    """
    await SmartWaterEntityHelper(hass, config_entry).async_setup_entry(Platform.BINARY_SENSOR, SmartWaterBinarySensor, async_add_entities)


class SmartWaterBinarySensor(CoordinatorEntity, BinarySensorEntity, SmartWaterEntity):
    """
    Representation of an entity that is part of a gateway, tank or pump.
    """

    def __init__(self, coordinator: SmartWaterCoordinator, device: SmartWaterData, key: str) -> None:
        """ 
        Initialize the sensor. 
        """

        CoordinatorEntity.__init__(self, coordinator)
        SmartWaterEntity.__init__(self, coordinator,  device, key)
        
        # The unique identifiers for this sensor within Home Assistant
        self.entity_id = ENTITY_ID_FORMAT.format(self._attr_unique_id)   # Device.name + params.key

        _LOGGER.debug(f"Create entity '{self.entity_id}'")
        
        # update creation-time only attributes
        self._attr_device_class = self.get_binary_sensor_device_class()

        # Link to the device
        self._attr_device_info = DeviceInfo(
            identifiers = {(DOMAIN, device.id)},
        )

        # Create all value related attributes
        data_value = device.get_value(key)
        self._update_value(data_value, force=True)
    
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """
        Handle updated data from the coordinator.
        """

        # find the correct device corresponding to this sensor
        devices:dict[str,SmartWaterData] = self._coordinator.data

        device = devices.get(self._device_id)
        if device is None:
            return        

        # Update value related attributes
        data_value = device.get_value(self._datapoint.key)

        if self._update_value(data_value):
            self.async_write_ha_state()
    
    
    def _update_value(self, data_value: Any, force:bool=False) -> bool:
        """
        Set entity value, unit and icon
        """
        changed = super()._update_value(data_value, force)

        # Convert from SmartWater data value to Home Assistant attributes
        if data_value in BINARY_SENSOR_VALUES_ON:
            is_on = True
        elif data_value in BINARY_SENSOR_VALUES_OFF:
            is_on = False
        else:
            is_on = None

        # Update Home Assistant attributes
        if force or self._attr_is_on != is_on:
            
            self._attr_is_on = is_on
            changed = True
        
        return changed
    
    
    