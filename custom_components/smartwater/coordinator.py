import logging

from datetime import datetime, timedelta
import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import async_get_hass
from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry
from homeassistant.helpers import entity_registry
from homeassistant.helpers.device_registry import DeviceRegistry
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_DEVICES,
)

from .const import (
    DOMAIN,
    NAME,
    COORDINATOR,
    MANUFACTURER,
    PREFIX_NAME,
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
)
from .data import (
    SmartWaterData,
    SmartWaterDataFamily,
    SmartWaterDataKey,
    SmartWaterDeviceConfig,
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
            coordinator = SmartWaterCoordinator(hass, config_entry, api, configs, options)

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
    

    @staticmethod
    async def async_close_temp(coordinator: 'SmartWaterCoordinator'):
        """
        Close a previously created coordinator
        """

        _LOGGER.debug("close temp coordinator")
        await SmartWaterApiFactory.async_close_temp(coordinator._api)
    

class SmartWaterCoordinator(DataUpdateCoordinator[dict[str,SmartWaterData]]):
    """My custom coordinator."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry, api: SmartWaterApiWrap, configs: dict[str,Any], options: dict[str,Any]):
        """
        Initialize my coordinator.
        """
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name=NAME,
            # This coordinator primarily depends on data pushed from the remote servers.
            # However, we also do an infrequent periodical poll from Web to detect added or removed devices.
            update_interval=timedelta(seconds=COORDINATOR_POLLING_INTERVAL),
            update_method=self._async_update_data,
        )

        self._config_entry: ConfigEntry = config_entry
        self._api: SmartWaterApiWrap = api
        self._configs: dict[str,Any] = configs
        self._options: dict[str,Any] = options

        self._profile_id = configs.get(CONF_PROFILE_ID, None)
        self._profile_name = configs.get(CONF_PROFILE_NAME, None)

        # Get devices from options
        device_config_dicts = options.get(CONF_DEVICES, [])
        self._device_configs: list[SmartWaterDeviceConfig] = [ SmartWaterDeviceConfig.from_dict(d) for d in device_config_dicts ]

        # Keep track of entity and device ids during init so we can cleanup unused ids later
        self._valid_unique_ids: dict[Platform, list[str]] = {} # platform -> entity unique_ids
        self._valid_device_ids: list[tuple[str,str]] = [] # list of HA device identifier

        # The data to return on requests from Entities
        self.data = self._get_data()

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
    def device_configs(self) -> list[SmartWaterDeviceConfig]:
        return self._device_configs
    

    @property
    def reload_count(self) -> int:
        return self._reload_count
    
    @reload_count.setter
    def reload_count(self, count: int):
        # Double the delay on each next reload to prevent enless reloads if something is wrong.
        self._reload_count = count
        self._reload_delay = min( pow(2,count-1)*COORDINATOR_RELOAD_DELAY, COORDINATOR_RELOAD_DELAY_MAX )


    def _get_data(self):
        """The data to return on requests from Entities"""
        return self._api.devices


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
        valid_ids: list[tuple[str,str]] = []

        for device in self._device_configs:
            _LOGGER.debug(f"Create device {device.id} ({device.name}) for profile '{self._profile_name}'")
 
            dr.async_get_or_create(
                config_entry_id = config_entry.entry_id,
                identifiers = {(DOMAIN, device.id)},
                name = f"{PREFIX_NAME} {device.name}",
                manufacturer =  MANUFACTURER,
                model = device.type,
                serial_number = device.serial,
                hw_version = device.version,
                via_device = (DOMAIN, device.gateway_id) if device.gateway_id is not None else None,
            )
            valid_ids.append( (DOMAIN, device.id) )

        # Remember valid device ids so we can do a cleanup of invalid ones later
        self._valid_device_ids = valid_ids


    async def async_cleanup_devices(self, config_entry: ConfigEntry):
        """
        cleanup all devices that are no longer in use
        """
        _LOGGER.info(f"Cleanup devices for profile '{self._profile_name}'")

        dr = device_registry.async_get(self.hass)
        registered_devices = device_registry.async_entries_for_config_entry(dr, config_entry.entry_id)

        for device in registered_devices:
            if all(id not in self._valid_device_ids for id in device.identifiers):
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

        The caller will handle exceptions.
        """
        _LOGGER.debug(f"Config flow data")
        await self._api.async_detect_data(force_relogin=True)  
        
        return self._api.profile, self._api.devices


    async def _async_update_data(self):
        """
        Poll for sensor data from API.

        Normally, sensor data will come in via our subscribed change handlers.
        However, we do an infrequent periodical poll to detect added or removed devices.
        """
        _LOGGER.info(f"Start detect of new gateways and devices for profile '{self._profile_name}'")
        try:
            await self._api.async_detect_data()
            await self._async_detect_changes()

        except Exception as ex:
            # Log issue. We expect it to be resolved on a next poll.
            _LOGGER.info(f"Failed to retrieve data for profile '{self._profile_name}'. Will retry later.")

        return self._get_data()
    

    async def async_subscribe_to_push_data(self):
        """
        Make sure we are subscribed to receive updated profile, gateways and devices (tanks and pumps)
        """
        _LOGGER.info(f"Subscribe to changes in devices for profile '{self._profile_name}")
        await self._api.async_subscribe_to_push_data(self._device_configs, self._async_push_data)


    @callback
    async def _async_push_data(self):
        """
        Push new sensor data from API to all our listening entities.
        """
        self.async_update_listeners()


    async def _async_detect_changes(self):
        """Detect changes in the profile and trigger a integration reload if needed"""

        # Deliberately delay reload checks to prevent enless reloads if something is wrong
        if (utcnow() - self._reload_time).total_seconds() < self._reload_delay:
            return

        # Update the existing entity_config with what is possibly new values
        data = self._config_entry.data
        options = self._config_entry.options

        if await self._async_detect_profile_changes():
            data[CONF_PROFILE_NAME] = self._api.profile.name

        if await self._async_detect_devices_changes():
            options[CONF_DEVICES] = [SmartWaterDeviceConfig.from_data(device_data).to_dict() for device_data in self._api.devices.values()]
            
        if self.hass.config_entries.async_update_entry(self.config_entry, data = data, options = options):
            # Now trigger a reload
            self._reload_count += 1
            self.hass.config_entries.async_schedule_reload(self._config_entry.entry_id)


    async def _async_detect_profile_changes(self) -> bool:
        """
        Detect any relevant changes in the profile. 
        Returns True if a reload needs to be triggered else False
        """
        if self._profile_name != self._api.profile.name:
            _LOGGER.info(f"Found change in profile name from '{self._profile_name}' to '{self._api.profile.name}'. Trigger reload of integration.")
            return True
        
        return False

        
    async def _async_detect_devices_changes(self)  -> bool:
        """
        Detect any new devices. 
        Returns True if a reload needs to be triggered else False
        """

        # Get list of device serials in HA device registry and as retrieved from Api
        api_ids: set[str] = set(self._api.devices.keys())
        old_ids: set[str] = set( [device_config.id for device_config in self.device_configs] )
        new_ids: set[str] = api_ids - old_ids

        # Log any newly found gateways or devices
        if len(new_ids) > 0:
            for new_id in new_ids:
                device = self._api.devices.get(new_id)
                _LOGGER.info(f"Found newly added {device.type} {device.id} ({device.name}) for profile '{self._profile_name}'. Trigger reload of integration.")
       
            return True

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
    
