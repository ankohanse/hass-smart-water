import asyncio
import logging
import math
from typing import Any

from homeassistant import config_entries
from homeassistant import exceptions
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorStateClass
from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.significant_change import check_percentage_change

from datetime import datetime
from datetime import timezone
from datetime import timedelta

from collections import defaultdict
from collections import namedtuple

from .const import (
    STATUS_VALIDITY_PERIOD,
    utcnow,
)
from .coordinator import (
    SmartWaterCoordinator,
)
from .data import (
    SmartWaterData,
    SmartWaterDeviceConfig,
)
from .entity_base import (
    SmartWaterEntity,
)
from .entity_helper import (
    SmartWaterEntityHelper,
)


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of sensor entities
    """
    await SmartWaterEntityHelper(hass, config_entry).async_setup_entry(Platform.SENSOR, SmartWaterSensor, async_add_entities)


class SmartWaterSensor(CoordinatorEntity, SensorEntity, SmartWaterEntity):
    """
    Representation of an entity that is part of a gateway, tank or pump.
    """
    
    def __init__(self, coordinator: SmartWaterCoordinator, device_config: SmartWaterDeviceConfig, key: str) -> None:
        """ 
        Initialize the sensor. 
        """

        CoordinatorEntity.__init__(self, coordinator)
        SmartWaterEntity.__init__(self, coordinator, device_config, key)

        # The unique identifiers for this sensor within Home Assistant
        self.entity_id = ENTITY_ID_FORMAT.format(self._attr_unique_id)   # Domain + Device.name + params.key
       
        _LOGGER.debug(f"Create entity '{self.entity_id}'")
        
        # update creation-time only attributes that are specific to class Sensor
        self._attr_state_class = self.get_sensor_state_class()
        self._attr_device_class = self.get_sensor_device_class() 
        
        # Create all value related attributes (but with unknown value).
        # After this constructor ends, base class SmartWaterEntity.async_added_to_hass() will 
        # set the value using the restored value from the last HA run. Or otherwise it will
        # be set when the first push-data is received.
        self._update_value(None, force=True)
    
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """
        Handle updated data from the coordinator.
        """

        # find the correct device corresponding to this sensor
        devices_data:dict[str,SmartWaterData] = self._coordinator.data

        device_date = devices_data.get(self._device_id)
        if device_date is None:
            return        

        # Update value related attributes
        data_value = device_date.get_value(self._datapoint.key)

        if self._update_value(data_value):
            self.async_write_ha_state()
    
    
    def _update_value(self, data_value: Any, force:bool=False) -> bool:
        """
        Set entity value, unit and icon
        """
        changed = super()._update_value(data_value, force)

        # Convert from SmartWater data value to Home Assistant attributes
        match self._datapoint.fmt:
            case 'f1' | 'f2' | 'f3' | 'f4':
                weight = 1
                attr_precision = int(self._datapoint.fmt.lstrip('f'))
                attr_val = round(float(data_value) * weight, attr_precision) if data_value is not None and isinstance(data_value, (float,int)) and not math.isnan(data_value) else None
                attr_unit = self._unit

            case 'i':
                weight = 1
                attr_precision = 0
                attr_val = int(data_value) * weight if data_value is not None and isinstance(data_value, int) and not math.isnan(data_value) else None
                attr_unit = self._unit

            case 't':
                attr_precision = None
                attr_val = datetime.fromtimestamp(float(data_value), timezone.utc) if data_value is not None and isinstance(data_value, (float,int)) and not math.isnan(data_value) else None
                attr_unit = None

            case 's':
                attr_precision = None
                attr_val = str(data_value) if data_value is not None else None
                attr_unit = None

            case 'e' | _:
                attr_precision = None
                attr_val = self._datapoint.opt.get(str(data_value), data_value) if data_value is not None and isinstance(self._datapoint.opt, dict) else None
                attr_unit = None

        # update Home Assistant attributes
        if force or self._attr_native_value != attr_val:

            self._attr_native_value = attr_val
            self._attr_native_unit_of_measurement = attr_unit
            self._attr_suggested_display_precision = attr_precision

            self._attr_icon = self.get_icon()
            changed = True
        
        return changed
    
