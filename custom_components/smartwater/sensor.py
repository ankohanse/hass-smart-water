import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .shared.entity_helper import SmartWaterEntityHelper
from .shared.sensor import SmartWaterSensor


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """
    Setting up the adding and updating of sensor entities
    """
    await SmartWaterEntityHelper(hass, config_entry).async_setup_entry(Platform.SENSOR, SmartWaterSensor, async_add_entities)
