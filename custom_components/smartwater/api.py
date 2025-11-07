"""api.py: API for Smart Water  integration."""

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Final
import httpx
import logging

from homeassistant.core import callback
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import create_async_httpx_client

from smartwater import (
    AsyncSmartWaterApi,
    SmartWaterApiFlag,
    SmartWaterConnectError,
    SmartWaterAuthError,
) 

from .const import (
    DOMAIN,
    API,
    API_RETRY_ATTEMPTS,
    API_RETRY_DELAY,
    STORE_KEY_CACHE,
    STORE_WRITE_PERIOD_CACHE,
    utcnow,
    utcmin,
)
from .data import (
    SmartWaterData,
    SmartWaterDataFamily,
    SmartWaterDataKey,
)
from .store import (
    SmartWaterStore,
)

# Define logger
_LOGGER = logging.getLogger(__name__)

class SmartWaterApiFactory:
    
    @staticmethod
    def create(hass: HomeAssistant, username: str, password: str) -> 'SmartWaterApiWrap':
        """
        Get a stored instance of the SmartWaterApi for given credentials
        """
    
        key = f"{username.lower()}_{hash(password) % 10**8}"
    
        # Sanity check
        if not DOMAIN in hass.data:
            hass.data[DOMAIN] = {}
        if not API in hass.data[DOMAIN]:
            hass.data[DOMAIN][API] = {}
            
        # if a DabPumpsApi instance for these credentials is already available then re-use it
        api = hass.data[DOMAIN][API].get(key, None)

        if not api or api.closed:
            _LOGGER.debug(f"create Api for account '{username}'")
            
            # Create a new SmartWaterApi instance and remember it
            api = SmartWaterApiWrap(hass, username, password)
            hass.data[DOMAIN][API][key] = api
        else:
            _LOGGER.debug(f"reuse Api for account '{username}'")

        return api
    

    @staticmethod
    def create_temp(hass: HomeAssistant, username: str, password: str) -> 'SmartWaterApiWrap':
        """
        Get a temporary instance of the SmartWaterApi for given credentials
        """

        key = f"{username.lower()}_{hash(password) % 10**8}"
    
        # Sanity check
        if not DOMAIN in hass.data:
            hass.data[DOMAIN] = {}
        if not API in hass.data[DOMAIN]:
            hass.data[DOMAIN][API] = {}
            
        # if a SmartWaterApi instance for these credentials is already available then re-use it
        api = hass.data[DOMAIN][API].get(key, None)
        
        if not api or api.closed:
            _LOGGER.debug(f"create temp Api")

            # Create a new SmartWaterApi instance
            api = SmartWaterApiWrap(hass, username, password, is_temp=True)
    
        return api    


    @staticmethod
    async def async_close_temp(api: 'SmartWaterApiWrap'):
        """
        Close a previously created SmartWaterApi
        """
        try:
            if api.is_temp and not api.closed:
                _LOGGER.debug("close temp Api")
                await api.close()

        except Exception as ex:
            _LOGGER.debug("Exception while closing temp Api: {ex}")


class SmartWaterFetchMethod(Enum):
    """Fetch methods"""
    WEB = 0     # slower, contains new data
    CACHE = 1   # faster, but old data

    def __str__(self):
        return self.name
    
    def __repr__(self):
        return self.name


class SmartWaterFetchOrder():
    """Fetch orders"""

    # On config, we try to fetch new data from web (slower)
    # No retries; if all login methods fail, we want to know immediately
    CONFIG: Final = ( SmartWaterFetchMethod.WEB, )   # Deliberate trailing comma to force create a tuple

    # On first fetch, we try to fetch old data from cache (faster) and 
    # fallback to fetch new data from web (slower and with two retries)
    # This allows for a faster startup of the integration
    INIT: Final = ( SmartWaterFetchMethod.CACHE, SmartWaterFetchMethod.WEB, SmartWaterFetchMethod.WEB, SmartWaterFetchMethod.WEB, )

    # On next fetches, we try to fetch new data from web (slower). 
    # No retries, next fetch will be 20 or 30 seconds later anyway. 
    # Also no need to read cached data; the api already contains these values.
    # Entities will display "unknown" once existing data gets too old.
    NEXT: Final = ( SmartWaterFetchMethod.WEB, )   # Deliberate trailing comma to force create a tuple

    # On change, we try to write the changed data to web (slower) with two retries
    CHANGE: Final = ( SmartWaterFetchMethod.WEB, SmartWaterFetchMethod.WEB, SmartWaterFetchMethod.WEB, )


class SmartWaterApiWrap(AsyncSmartWaterApi):
    """Wrapper around smartwater AsyncSmartWaterApi class"""

    def __init__(self, hass: HomeAssistant, username: str, password: str, is_temp: bool = False):
        """Initialize the api"""

        self._hass = hass
        self._username = username
        self._password = password
        self.is_temp = is_temp

        # Create a fresh http client
        client: httpx.AsyncClient = create_async_httpx_client(hass) 
        
        # Initialize the actual api
        flags = {
            SmartWaterApiFlag.REFRESH_HANDLER_START: True if not is_temp else False,
            SmartWaterApiFlag.DIAGNOSTICS_COLLECT: True
        } 
        super().__init__(username, password, client=client, flags=flags)

        # Data properties
        self.profile: SmartWaterData = SmartWaterData(family=SmartWaterDataFamily.PROFILE, id="", data={}, context={})
        self.devices: dict[str,SmartWaterData] = {}

        # Coordinator listener to report back any changes in the data
        self._async_data_listener = None

        # Persisted cached data in case communication to DAB Pumps fails
        self._hass: HomeAssistant = hass
        self._cache: SmartWaterStore = SmartWaterStore(hass, STORE_KEY_CACHE, STORE_WRITE_PERIOD_CACHE)

        # Counters for diagnostics
        self._diag_retries: dict[int, int] = { n: 0 for n in range(API_RETRY_ATTEMPTS) }
        self._diag_durations: dict[int, int] = { n: 0 for n in range(10) }
        self._diag_fetch: dict[str, int] = { n.name: 0 for n in SmartWaterFetchMethod }


    async def async_on_unload(self, profile_id:str):
        """
        Called when the integration is being stopped/restarted
        """
        # Do not logout or close the api. Another coordinator/config-entry might still be using it.
        # But do trigger write of cache
        await self._async_write_cache(profile_id, force=True)


    async def async_detect_for_config(self):
        """
        Validate login credentials and retrieve the user profile.
        Only used during config flow and always uses polling with no use of cache and no retry attempts
        """
        dt_start = utcnow()

        # Logout so we really force a subsequent login and not use an old token
        await self._async_logout()
        await self._async_login()

        # Once login succeeds we have a profile_id
        # Fetch the profile
        await self._async_poll_profile(super().profile_id)

        # If we reach this point then the detect was successfull.
        # Otherwise exceptions are handled by the callers.
    
        
    async def async_detect_data(self, profile_id: str, fetch_order: SmartWaterFetchOrder):
        """
        We mostly rely on the remote servers notifying us of changes of data (push).

        However, we do an initial poll from Cache (with retries from Web) to retrieve the
        initial list of devices and their entity data.
        After that we do an infrequent periodical poll from Web to detect added or removed devices.
        """
        ex_first = None
        dt_start = utcnow()

        for retry,fetch_method in enumerate(fetch_order):
            try:
                # Retry handling
                await self._async_handle_retry(retry, fetch_method, fetch_order)

                match fetch_method:
                    case SmartWaterFetchMethod.WEB:
                        await self._async_poll_profile(profile_id)
                        await self._async_poll_profile_devices(profile_id)

                        # Update the persisted cache
                        await self._async_write_cache(profile_id)

                    case SmartWaterFetchMethod.CACHE:
                        await self._async_read_cache(profile_id)

                # Keep track of how many retries were needed and duration
                # Keep track of how often the successfull fetch is from Web or is from Cache
                self._update_statistics(retries = retry, duration = utcnow()-dt_start, fetch = fetch_method)

                return True
            
            except Exception as ex:
                _LOGGER.debug(ex)
                if not ex_first:
                    ex_first = ex
                await self._async_logout()

        if ex_first:
            if isinstance(ex_first, (SmartWaterConnectError,SmartWaterAuthError)):
                # Log as info, not warning, as we expect the issue to be gone at a next data refresh
                _LOGGER.info(ex_first)
            else:
                _LOGGER.warning(ex_first)
        
        # Keep track of how many retries were needed and duration
        self._update_statistics(retries = retry, duration = utcnow()-dt_start)
        return False
    

    async def _async_handle_retry(self, retry: int, fetch_method: SmartWaterFetchMethod, fetch_order: SmartWaterFetchOrder):
        """
        """
        if retry == 0:
            # This is not a retry, but the first attempt
            return

        fetch_history: tuple[SmartWaterFetchMethod] = fetch_order[slice(retry)]

        if fetch_method in fetch_history:
            # Wait a bit before the next fetch using same method
            _LOGGER.info(f"Retry from {str(fetch_method)} in {API_RETRY_DELAY} seconds.")
            await asyncio.sleep(API_RETRY_DELAY)
        else:
            _LOGGER.info(f"Retry from {str(fetch_method)} now")


    async def _async_login(self):
        """Login"""
        await super().login()


    async def _async_logout(self):
        """Logout"""
        await super().logout()


    async def _async_poll_profile(self, profile_id:str):
        """
        Attempt to refresh the profile
        """
        profile_data = await super().fetch_profile()

        self._on_profile_change(profile_id, profile_data)


    async def _async_poll_profile_devices(self, profile_id:str):
        """
        Fetch all gateways and all devices in a profile
        """
        old_device_ids = set(self.devices.keys())
        new_device_ids = set()

        # Fetch all gateways in this profile
        gateways_data = await super().fetch_gateways()

        for gateway_id,gateway_data in gateways_data.items():
            await self._async_on_device_change(SmartWaterDataFamily.GATEWAY, gateway_id, gateway_data)
            new_device_ids.add(gateway_id)

            # Fetch all devices for this gateway
            gw_devices_data = await super().fetch_devices(gateway_id)

            for device_id,device_data in gw_devices_data.items():
                await self._async_on_device_change(SmartWaterDataFamily.DEVICE, device_id, device_data)
                new_device_ids.add(device_id)

        # Cleanup - remove any old devices that we don't see anymore
        del_device_ids = old_device_ids - new_device_ids
        for id in del_device_ids:
            self.devices.pop(id, None)


    async def async_subscribe_to_push_data(self, profile_id: str, callback):
        """
        Subscribe to changes in profile. gateway and devices (tanks and pumps)
        """
        try:
            # Remember how to report back data changes to the coordinator
            self._async_data_listener = callback

            # Register listeners for changes in remote data
            await super().on_profile(self._on_profile_change)

            for device_id, device in self.devices.items():
                match device.family:
                    case SmartWaterDataFamily.GATEWAY: await super().on_gateway(device_id, self._on_gateway_change)
                    case SmartWaterDataFamily.DEVICE:  await super().on_device(device_id, self._on_device_change)

        except Exception as e:
            _LOGGER.info(f"{e}")


    def _on_profile_change(self, profile_id: str, profile_data: dict):
        """
        AsyncSmartWaterApi.on_profile() needs a sync callback function.
        We jump back into the async event loop here.
        """
        self._hass.create_task(self._async_on_profile_change(profile_id, profile_data))


    async def _async_on_profile_change(self, profile_id: str, profile_data: dict):
        """Handle updated profile received from the remote servers"""
        try:
            context = {
                'username': self._username,
            }
            self.profile = SmartWaterData(family=SmartWaterDataFamily.PROFILE, id=profile_id, data=profile_data, context=context)

            _LOGGER.debug(f"Received profile data for {self._username} ({profile_id})")

            # Signal to the coordinator that there were changes in the api data
            if self._async_data_listener is not None:
                await self._async_data_listener()

        except Exception as e:
            _LOGGER.info(f"{e}")


    def _on_gateway_change(self, gateway_id: str, gateway_data: dict):
        """
        AsyncSmartWaterApi.on_gateway() needs a sync callback function.
        We jump back into the async event loop here.
        """
        self._hass.create_task(self._async_on_device_change(SmartWaterDataFamily.GATEWAY, gateway_id, gateway_data))
        

    def _on_device_change(self, device_id: str, device_data: dict):
        """
        AsyncSmartWaterApi.on_device() needs a sync callback function.
        We jump back into the async event loop here.
        """
        self._hass.create_task(self._async_on_device_change(SmartWaterDataFamily.DEVICE, device_id, device_data))
        

    async def _async_on_device_change(self, device_family, device_id: str, device_data: dict):
        """Handle updated device (gateway, tank or pump) received from the remote servers"""
        try:
            context = {
                "profile_id": super().profile_id,
            }
            device = SmartWaterData(family=device_family, id=device_id, data=device_data, context=context) 
        
            _LOGGER.debug(f"Received device data for {device.name} ({device.id})")
            self.devices[device.id] = device

            # Signal to the coordinator that there were changes in the api data
            if self._async_data_listener is not None:
                await self._async_data_listener()

        except Exception as e:
            _LOGGER.info(f"{e}")


    async def _async_write_cache(self, profile_id:str, force:bool=False):
        """
        Write data retrieved from api to persisted storage
        """
 
        # Make sure we have read the storage file before we attempt set values and write it
        await self._cache.async_read()

        # Set the updated values
        profile_dict = self.profile.to_dict()
        devices_dict = { id:device.to_dict() for id,device in self.devices.items() }
        
        self._cache.set(f"profile {profile_id}", profile_dict )
        self._cache.set(f"devices {profile_id}", devices_dict )

        # Note that async_write will reduce the number of writes if needed.
        await self._cache.async_write(force)


    async def _async_read_cache(self, profile_id: str):
        """
        Read internal data from persisted storage
        """             

        # Read from persisted file if not already read
        await self._cache.async_read()

        # Get all mappings, these will be returned as pure dicts and need to be converted into the proper dataclasses
        profile_dict = self._cache.get(f"profile {profile_id}", {})
        devices_dict = self._cache.get(f"devices {profile_id}", {})

        if not profile_dict or not devices_dict:
            raise Exception(f"Not all data found in {self._cache.key}")

        self.profile = SmartWaterData.from_dict(profile_dict)
        self.devices = { id:SmartWaterData.from_dict(device_dict) for id,device_dict in devices_dict.items() }


    def _update_statistics(self, retries: int|None = None, duration: timedelta|None = None, fetch: SmartWaterFetchMethod|None = None):
        """
        Update internal counters used for diagnostics
        """
        if retries is not None:
            if retries in self._diag_retries:
                self._diag_retries[retries] += 1
            else:
                self._diag_retries[retries] = 1
            
        if duration is not None:
            duration = round(duration.total_seconds(), 0)
            if duration not in self._diag_durations:
                self._diag_durations[duration] = 1
            else:
                self._diag_durations[duration] += 1

        if fetch is not None:
            if fetch.name not in self._diag_fetch:
                self._diag_fetch[fetch.name] = 1
            else:
                self._diag_fetch[fetch.name] += 1


    async def async_get_diagnostics(self) -> dict[str, Any]:

        retries_total = sum(self._diag_retries.values()) or 1
        retries_counter = dict(sorted(self._diag_retries.items()))
        retries_percent = { key: round(100.0 * n / retries_total, 2) for key,n in retries_counter.items() }

        durations_total = sum(self._diag_durations.values()) or 1
        durations_counter = dict(sorted(self._diag_durations.items()))
        durations_percent = { key: round(100.0 * n / durations_total, 2) for key, n in durations_counter.items() }

        fetch_total = sum(self._diag_fetch.values()) or 1
        fetch_counter = dict(sorted(self._diag_fetch.items()))
        fetch_percent = { key: round(100.0 * n / fetch_total, 2) for key, n in fetch_counter.items() }

        diag = await super().get_diagnostics()

        diag["data"].update( {
            "profile": self.profile.to_dict(),
            "devices": [ d.to_dict() for d in self.devices.values() ],
        } )
        diag["cache"] = await self._cache.async_get_diagnostics()
        diag["diagnostics"].update( {
                "ts": utcnow(),
                "retries": {
                    "counter": retries_counter,
                    "percent": retries_percent,
                },
                "durations": {
                    "counter": durations_counter,
                    "percent": durations_percent,
                },
                "fetch": {
                    "counter": fetch_counter,
                    "percent": fetch_percent,
                },
        })

        return diag
   






