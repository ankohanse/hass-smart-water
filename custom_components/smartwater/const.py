"""Constants for the DAB Pumps integration."""
from datetime import datetime, timezone
import logging

from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
)
from homeassistant.const import Platform


_LOGGER: logging.Logger = logging.getLogger(__package__)


# Base component constants
DOMAIN = "smartwater"
NAME = "Smart Water"
ISSUE_URL = "https://github.com/ankohanse/hass-smartwater/issues"

# Map platform to pf codes for both enabled and disabled entities
PLATFORM_TO_PF: dict[Platform, str] = {
    Platform.SENSOR:        "sen",
    Platform.BINARY_SENSOR: "bin",
}
PLATFORMS = list(PLATFORM_TO_PF.keys())

HUB = "Hub"
API = "Api"
COORDINATOR = "Coordinator"

DEFAULT_USERNAME = ""
DEFAULT_PASSWORD = ""

CONF_PROFILE_ID = "profile_id"
CONF_PROFILE_NAME = "profile_name"

STORE_KEY_CACHE = "cache"
STORE_WRITE_PERIOD_CACHE = 300 # seconds

DIAGNOSTICS_REDACT = { CONF_PASSWORD, 'client_secret' }

MANUFACTURER = "Smart Water Technologies"

# Extra attributes that are restored from the previous HA run
ATTR_STORED_CODE = "code"
ATTR_STORED_VALUE = "value"

BINARY_SENSOR_VALUES_ON = [True, 1, '1']
BINARY_SENSOR_VALUES_OFF = [False, 0, '0']
BINARY_SENSOR_VALUES_ALL = BINARY_SENSOR_VALUES_ON + BINARY_SENSOR_VALUES_OFF

API_RETRY_ATTEMPTS = 2
API_RETRY_DELAY = 5    # seconds

COORDINATOR_RELOAD_DELAY = 1*60*60 # 1 hour in seconds
COORDINATOR_RELOAD_DELAY_MAX = 24*60*60 # 24 hours in seconds

STATUS_VALIDITY_PERIOD = 15*60 # 15 minutes in seconds

# Global helper functions
utcnow = lambda: datetime.now(timezone.utc)
utcmin = lambda: datetime.min.replace(tzinfo=timezone.utc)


