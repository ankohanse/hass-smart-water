import logging

from datetime import datetime, timedelta
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.core import async_get_hass
from homeassistant.helpers import device_registry
from homeassistant.helpers import entity_registry
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
)

from .const import (
    DOMAIN,
    NAME,
    COORDINATOR,
    MANUFACTURER,
    CONF_PROFILE_ID,
    CONF_PROFILE_NAME,
    COORDINATOR_POLLING_INTERVAL,
    COORDINATOR_RELOAD_DELAY,
    COORDINATOR_RELOAD_DELAY_MAX,
    utcnow,
)
from .api import (
    SmartWaterApiFactory,
    SmartWaterApiWrap,
    SmartWaterFetchOrder,
)
from .data import (
    SmartWaterData,
    SmartWaterDataFamily,
    SmartWaterDataKey,
)


# Define logger
_LOGGER = logging.getLogger(__name__)

class SmartWaterCoordinatorFactory:
    """Factory to help create the Coordinator"""

    @staticmethod
    def create(hass: HomeAssistant, config_entry: ConfigEntry, force_create: bool = False):
        """
        Get existing Coordinator for a config entry, or create a new one if it does not yet exist
        """
    
        # Get properties from the config_entry
        configs = config_entry.data
        options = config_entry.options

        username = configs.get(CONF_USERNAME, None)
        password = configs.get(CONF_PASSWORD, None)
        profile_id = configs.get(CONF_PROFILE_ID, None)
        profile_name = configs.get(CONF_PROFILE_NAME, None)

        reload_count = 0
        
        # Sanity check
        if not DOMAIN in hass.data:
            hass.data[DOMAIN] = {}
        if not COORDINATOR in hass.data[DOMAIN]:
            hass.data[DOMAIN][COORDINATOR] = {}
            
        # already created?
        coordinator = hass.data[DOMAIN][COORDINATOR].get(profile_id, None)
        if coordinator:
            # check for an active reload and copy reload settings when creating a new coordinator
            reload_count = coordinator.reload_count

            # Forcing a new coordinator?
            if force_create:
                coordinator = None

            # Verify that config and options are still the same (== and != do a recursive dict compare)
            elif coordinator.configs != configs or coordinator.options != options:
                # Not the same; force recreate of the coordinator
                _LOGGER.debug(f"Settings have changed; force use of new coordinator")
                coordinator = None

        if not coordinator:
            _LOGGER.debug(f"Create coordinator for profile '{profile_name}' ({profile_id}) from account '{username}'")

            # Get an instance of the SmartWaterApi for these credentials
            # This instance may be shared with other coordinators that use the same credentials
            api = SmartWaterApiFactory.create(hass, username, password)
        
            # Get an instance of our coordinator. This is unique to this profile_id
            coordinator = SmartWaterCoordinator(hass, config_entry.entry_id, api, configs, options)

            # Apply reload settings if needed
            coordinator.reload_count = reload_count

            hass.data[DOMAIN][COORDINATOR][profile_id] = coordinator
        else:
            _LOGGER.debug(f"Reuse coordinator for profile '{profile_name}' ({profile_id})")
            
        return coordinator


    @staticmethod
    def create_temp(username: str, password: str):
        """
        Get temporary Coordinator for a given username+password.
        This coordinator will only provide limited functionality
        """
    
        # Get properties from the config_entry
        hass = async_get_hass()
        configs = {
            CONF_USERNAME: username,
            CONF_PASSWORD: password,
        }
        options = {}
        
        # Get a temporary instance of the DabPumpsApi for these credentials
        api = SmartWaterApiFactory.create_temp(hass, username, password)
        
        # Get an instance of our coordinator. This is unique to this profile_id
        _LOGGER.debug(f"create temp coordinator for account '{username}'")
        coordinator = SmartWaterCoordinator(hass, None, api, configs, options)
        return coordinator
    

class SmartWaterCoordinator(DataUpdateCoordinator[dict[str,SmartWaterData]]):
    """My custom coordinator."""

    def __init__(self, hass: HomeAssistant, config_entry_id: str, api: SmartWaterApiWrap, configs: dict[str,Any], options: dict[str,Any]):
        """
        Initialize my coordinator.
        """
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=NAME,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=COORDINATOR_POLLING_INTERVAL),
            update_method=self._async_update_data,
        )

        self._config_entry_id: str = config_entry_id
        self._api: SmartWaterApiWrap = api
        self._configs: dict[str,Any] = configs
        self._options: dict[str,Any] = options

        self._profile_id = configs.get(CONF_PROFILE_ID, None)
        self._profile_name = configs.get(CONF_PROFILE_NAME, None)

        self._fetch_order = SmartWaterFetchOrder.INIT

        # Keep track of entity and device ids during init so we can cleanup unused ids later
        self._valid_unique_ids: dict[Platform, list[str]] = {} # platform -> entity unique_id
        self._valid_device_ids: dict[str, tuple[str,str]] = {} # serial -> HA device identifier

        # Auto reload when a new device is detected
        self._reload_count: int = 0
        self._reload_time: datetime = utcnow()
        self._reload_delay: int = COORDINATOR_RELOAD_DELAY


    @property
    def configs(self) -> dict[str,Any]:
        return self._configs
    

    @property
    def options(self) ->dict[str,Any]:
        return self._options
    

    @property
    def profile_id(self) -> str:
        return self._profile_id
    

    @property
    def profile_name(self) -> str:
        return self._profile_name
    

    @property
    def reload_count(self) -> int:
        return self._reload_count
    
    @reload_count.setter
    def reload_count(self, count: int):
        # Double the delay on each next reload to prevent enless reloads if something is wrong.
        self._reload_count = count
        self._reload_delay = min( pow(2,count-1)*COORDINATOR_RELOAD_DELAY, COORDINATOR_RELOAD_DELAY_MAX )
    

    async def async_on_unload(self):
        """
        Called when Home Assistant shuts down or config-entry unloads
        """
        _LOGGER.info(f"Unload profile '{self._profile_name}'")

        # Do not logout or close the api. Another coordinator/config-entry might still be using it.
        # But do trigger write of cache
        await self._api.async_on_unload(self._profile_id)


    def set_valid_unique_ids(self, platform: Platform, ids: list[str]):
        """
        Set list of valid entity ids for this profile.
        Called from entity_base when all entities for a platform have been created.
        """
        self._valid_unique_ids[platform] = ids


    async def async_create_devices(self, config_entry: ConfigEntry):
        """
        Add all detected devices to the hass device_registry
        """

        _LOGGER.info(f"Create devices for profile '{self._profile_name}'")
        dr: DeviceRegistry = device_registry.async_get(self.hass)
        valid_ids: dict[str, tuple[str,str]] = {}

        for device in self._api.devices.values():

            device_id = device.id
            device_name = device.name
            device_type = device.get_value(SmartWaterDataKey.TYPE)
            device_serial = device.get_value(SmartWaterDataKey.SERIAL)  
            device_version = device.get_value(SmartWaterDataKey.VERSION)
            device_gw_id = device.get_value(SmartWaterDataKey.GATEWAY_ID) # only for Tanks and Pumps

            _LOGGER.debug(f"Create device {device_id} ({device_name}) for profile '{self._profile_name}'")

            dr.async_get_or_create(
                config_entry_id = config_entry.entry_id,
                identifiers = {(DOMAIN, device_id)},
                name = device_name,
                manufacturer =  MANUFACTURER,
                model = device_type,
                serial_number = device_serial or device_id,
                hw_version = device_version,
                via_device = (DOMAIN, device_gw_id) if device_gw_id is not None else None,
            )
            valid_ids[device_id] = (DOMAIN, device_id)

        # Remember valid device ids so we can do a cleanup of invalid ones later
        self._valid_device_ids = valid_ids


    async def async_cleanup_devices(self, config_entry: ConfigEntry):
        """
        cleanup all devices that are no longer in use
        """
        _LOGGER.info(f"Cleanup devices for profile '{self._profile_name}'")
        valid_identifiers = list(self._valid_device_ids.values())

        dr = device_registry.async_get(self.hass)
        registered_devices = device_registry.async_entries_for_config_entry(dr, config_entry.entry_id)

        for device in registered_devices:
            if all(id not in valid_identifiers for id in device.identifiers):
                _LOGGER.info(f"Remove obsolete device {next(iter(device.identifiers))} from profile '{self._profile_name}'")
                dr.async_remove_device(device.id)


    async def async_cleanup_entities(self, config_entry: ConfigEntry):
        """
        cleanup all entities within this profile that are no longer in use
        """
        _LOGGER.info(f"Cleanup entities for profile '{self._profile_name}'")

        er = entity_registry.async_get(self.hass)
        registered_entities = entity_registry.async_entries_for_config_entry(er, config_entry.entry_id)

        for entity in registered_entities:
            # Retrieve all valid ids matching the platform of this registered entity.
            # Note that platform and domain are mixed up in entity_registry
            valid_unique_ids = self._valid_unique_ids.get(entity.domain, [])

            if entity.unique_id not in valid_unique_ids:
                _LOGGER.info(f"Remove obsolete entity {entity.entity_id} ({entity.unique_id}) from profile '{self._profile_name}'")
                er.async_remove(entity.entity_id)


    async def async_config_flow_data(self):
        """
        Fetch profile data from API.
        """
        _LOGGER.debug(f"Config flow data")

        await self._api.async_detect_for_config()  
        
        #_LOGGER.debug(f"profile: {self._api.profile}")
        return self._api.profile


    async def _async_update_data(self):
        """
        Fetch sensor data from API.
        
        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        _LOGGER.debug(f"Update data for profile '{self._profile_name}'")

        # Fetch the actual data
        # Note: asyncio.TimeoutError and aiohttp.ClientError are already
        # handled by the data update coordinator.
        await self._api.async_detect_data(self._profile_id, self._fetch_order)

        # If this was the first fetch, then make sure all next ones use the correct fetch order (web or cache)
        self._fetch_order = SmartWaterFetchOrder.NEXT

        # Periodically detect changes in the profile and devices and trigger reload of the integration if needed.
        await self._async_detect_changes()

        return self._api.devices
    
    
    async def _async_detect_changes(self):
        """Detect changes in the profile and trigger a integration reload if needed"""

        # Deliberately delay reload checks to prevent enless reloads if something is wrong
        if (utcnow() - self._reload_time).total_seconds() < self._reload_delay:
            return

        # Detect any changes
        reload = await self._async_detect_profile_changes()
        if reload:
            self._reload_count += 1
            self.hass.config_entries.async_schedule_reload(self._config_entry_id)

        
    async def _async_detect_profile_changes(self)  -> bool:
        """
        Detect any new devices. Returns True if a reload needs to be triggered else False
        """

        # Get list of device serials in HA device registry and as retrieved from Api
        api_ids: set[str] = set(self._api.devices.keys())
        old_ids: set[str] = set(self._valid_device_ids.keys())
        new_ids: set[str] = api_ids - old_ids

        for new_id in new_ids:
            device = self._api.devices.get(new_id)
            device_name = device.get_value(SmartWaterDataKey.NAME) or "unknown"
            device_type = device.get_value(SmartWaterDataKey.TYPE) or "device"

            match device.family:
                case SmartWaterDataFamily.GATEWAY:
                    _LOGGER.info(f"Found newly added gateway {device.id} ({device_name}) for profile '{self._profile_name}'. Trigger reload of integration.")
                case SmartWaterDataFamily.DEVICE | _:
                    _LOGGER.info(f"Found newly added {device_type} {device.id} ({device_name}) for profile '{self._profile_name}'. Trigger reload of integration.")

        if len(new_ids) > 0:
            return True
        else:            
            return False


    async def async_get_diagnostics(self) -> dict[str, Any]:
        """
        Get all diagnostics values
        """
        return {
            "data": {
                "profile_id": self._profile_id,
            },
            "diagnostics": {
                "reload_count": self.reload_count,
            },
        }
    
