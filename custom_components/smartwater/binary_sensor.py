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

from .shared.entity_helper import SmartWaterEntityHelper
from .shared.binary_sensor import SmartWaterBinarySensor


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

  
    