import logging
import re

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.const import PERCENTAGE
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.const import UnitOfInformation
from homeassistant.const import UnitOfElectricCurrent
from homeassistant.const import UnitOfElectricPotential
from homeassistant.const import UnitOfEnergy
from homeassistant.const import UnitOfLength
from homeassistant.const import UnitOfPower
from homeassistant.const import UnitOfPressure
from homeassistant.const import UnitOfVolume
from homeassistant.const import UnitOfVolumeFlowRate
from homeassistant.const import UnitOfTemperature
from homeassistant.const import UnitOfTime
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity

from .const import (
    DOMAIN,
    ATTR_DATA_VALUE,
    ATTR_STORED_DATA_VALUE,
    PREFIX_ID,
    utcnow,
)
from .coordinator import (
    SmartWaterCoordinator,
)
from .data import (
    SmartWaterData,
)

# Define logger
_LOGGER = logging.getLogger(__name__)


@dataclass
class SmartWaterEntityExtraData(ExtraStoredData):
    """Object to hold extra stored data."""
    data_value: Any = None
    
    def as_dict(self) -> dict[str, Any]:
        """Return a dict representation of the sensor data."""
        return {
            ATTR_STORED_DATA_VALUE: self.data_value
        }

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self | None:
        """Initialize a stored sensor state from a dict."""
        return cls(
            data_value = restored.get(ATTR_STORED_DATA_VALUE)
        )


class SmartWaterEntity(RestoreEntity):
    """
    Common funcionality for all Entities:
    (SmartWaterSensor, SmartWaterBinarySensor, ...)
    """
    
    def __init__(self, coordinator: SmartWaterCoordinator, device: SmartWaterData, key: str):

        self._coordinator = coordinator
        self._device_id = device.id
        
        # Remember the static meta parameters for this entity
        self._datapoint = device.get_datapoint(key)

        # The unique identifiers for this sensor within Home Assistant
        self.object_id       = SmartWaterEntity.create_id(PREFIX_ID, device.id, key)   # smartwater_<device_id>_<key>
        self._attr_unique_id = SmartWaterEntity.create_id(PREFIX_ID, device.name, key) # smartwater_<device_name>_<key>

        self._attr_has_entity_name = True
        self._attr_name = self._datapoint.name
        self._name = self._datapoint.name

        # Attributes to be restored in the next HA run
        self._data_value: Any = None     # Original data value as returned from Api

        # Derived properties
        self._unit = self.get_unit()        # don't apply directly to _attr_unit, some entities don't have it
        self._attr_icon = self.get_icon()

        self._attr_entity_registry_enabled_default = self.get_entity_enabled_default()
        self._attr_entity_category = self.get_entity_category()

        # Link to the device
        self._attr_device_info = DeviceInfo(
            identifiers = {(DOMAIN, device.id)},
        )


    @property
    def suggested_object_id(self) -> str | None:
        """Return input for object id."""
        return self.object_id


    @property
    def extra_state_attributes(self) -> dict[str, str | list[str]]:
        """
        Return the state attributes to display in entity attributes.
        """
        state_attr = {}

        if self._data_value is not None:
            state_attr[ATTR_DATA_VALUE] = self._data_value

        return state_attr        


    @property
    def extra_restore_state_data(self) -> SmartWaterEntityExtraData | None:
        """
        Return entity specific state data to be restored on next HA run.
        """
        return SmartWaterEntityExtraData(
            data_value = self._data_value
        )
    

    @staticmethod
    def create_id(*args):
        str = '_'.join(args).strip('_')
        str = re.sub(' ', '_', str)
        str = re.sub('[^a-z0-9_-]+', '', str.lower())
        return str            
    
    
    async def async_added_to_hass(self) -> None:
        """
        Handle when the entity has been added
        """
        await super().async_added_to_hass()

        # Get last data from previous HA run                      
        last_state = await self.async_get_last_state()
        last_extra = await self.async_get_last_extra_data()
        
        if last_state and last_extra:
            # Get entity value from restored data
            dict_extra = last_extra.as_dict()
            data_value = dict_extra.get(ATTR_STORED_DATA_VALUE)

            self._update_value(data_value, force=True)
    

    def _update_value(self, data_value: Any, force:bool=False) -> bool:
        """
        Process any changes in value
        
        To be extended by derived entities
        """
        changed = False

        if force or self._data_value != data_value:

            self._data_value = data_value
            changed = True

        return changed


    def get_unit(self):
        """Convert from Datapoint unit abbreviation to Home Assistant units"""
        if self._datapoint is None:
            return None
        
        match self._datapoint.unit:
            case 'd':           return UnitOfTime.DAYS
            case 'month':       return UnitOfTime.MONTHS
            case '%':           return PERCENTAGE
            case 'm':           return UnitOfLength.METERS
            case 'V':           return UnitOfElectricPotential.VOLT
            case 'dB':          return SIGNAL_STRENGTH_DECIBELS
            case 'dBm':         return SIGNAL_STRENGTH_DECIBELS_MILLIWATT
            case '' | None:     return None
            
            case _:
                _LOGGER.warning(f"Encountered a unit or measurement '{self._datapoint.unit}' for '{self._datapoint.fam}:{self._datapoint.key}' that may not be supported by Home Assistant. Please contact the integration developer to have this resolved.")
                return self._datapoint.unit
    
    
    def get_icon(self):
        """Convert from unit to icon"""
        match self._datapoint.key:
            case 'battery_level':  return None  # Automatically assigned by HA with battery-low, battery-med or battery-high
            case 'water_level':    return 'mdi:water-percent'
            case 'trend_level':    return { 'flat':'mdi:waves', 'up':'mdi:waves-arrow-up', 'down': 'mdi:waves-arrow-down' }.get(self._data_value, None)

        match self._datapoint.unit:
            case 'd':       return 'mdi:timer'
            case 'month':   return 'mdi:calendar-clock'
            case '%':       return 'mdi:percent'
            case 'm':       return 'mdi:arrow-expand-vertical'
            case 'V':       return 'mdi:lightning-bolt'
            case 'dB':      return 'mdi:antenna'
            case 'dBm':     return 'mdi:signal'
            case _:         return None
    
    
    def get_number_device_class(self):
        """Convert from unit to NumberDeviceClass"""
        match self._datapoint.unit:
            case '%':       return None 
            case 'd':       return None
            case 'month':   return None
            case 'm':       return NumberDeviceClass.DISTANCE
            case 'V':       return NumberDeviceClass.VOLTAGE
            case 'dB':      return NumberDeviceClass.SIGNAL_STRENGTH
            case 'dBm':     return NumberDeviceClass.SIGNAL_STRENGTH
            case _:         return None
    
    
    def get_sensor_device_class(self):
        """Convert from unit to SensorDeviceClass"""
        match self._datapoint.key:
            case 'battery_level': return NumberDeviceClass.BATTERY

        match self._datapoint.fmt:
            case 's':       return SensorDeviceClass.ENUM
            case 'e':       return SensorDeviceClass.ENUM
            case 't':       return SensorDeviceClass.TIMESTAMP
            
        match self._datapoint.unit:
            case '%':       pass
            case 'd':       return None
            case 'month':   return None
            case 'm':       return SensorDeviceClass.DISTANCE
            case 'V':       return SensorDeviceClass.VOLTAGE
            case 'dB':      return SensorDeviceClass.SIGNAL_STRENGTH
            case 'dBm':     return SensorDeviceClass.SIGNAL_STRENGTH
            case _:         return None

    
    def get_binary_sensor_device_class(self):
        """Return one of the BinarySensorDeviceClass.xyz or None"""
        match self._datapoint.key:
            case 'aux_power':                       return BinarySensorDeviceClass.POWER
            case key if key.startswith("alert_"):   return BinarySensorDeviceClass.PROBLEM
            case _:                                 return None

    
    def get_sensor_state_class(self):
        # Return StateClass=None for Enum, Label or timestamp
        match self._datapoint.fmt:
            case 's':       return None
            case 'e':       return None
            case 't':       return None

        match self._datapoint.unit:
            case _:         return SensorStateClass.MEASUREMENT
    
    
    def get_entity_category(self):
        # Return EntityCategory as configured in DATASET
        match self._datapoint.flag_category:
            case "conf":    return EntityCategory.CONFIG
            case "diag":    return EntityCategory.DIAGNOSTIC
            case "none":    return None
            case _:         return None


    def get_entity_enabled_default(self):
        # Return EntityEnabled as configured in DATASET
        match self._datapoint.flag_enabled:
            case 'd': return False
            case 'e': return True
            case _:   return True

