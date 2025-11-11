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
    SmartWaterDeviceConfig,
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
        self.profile: SmartWaterData = SmartWaterData(family=SmartWaterDataFamily.PROFILE, id="", dict={}, context={})
        self.devices: dict[str,SmartWaterData] = {}

        # Coordinator listener to report back any changes in the data
        self._async_data_listener = None


    async def async_detect_data(self, force_relogin:bool = False):
        """
        We mostly rely on the remote servers notifying us of changes of data (push).
        However, we do an infrequent periodical poll to detect added or removed devices.
        """
        # Logout so we really force a subsequent login and not use an old token
        if force_relogin:
            await self._async_logout()
    
        # Login and get profile_id
        profile_id = await self._async_login()

        # Fetch the profile and all devices (gateways, tanks, pumps)
        await self._async_poll_profile(profile_id)
        await self._async_poll_profile_devices(profile_id)
    

    async def _async_login(self):
        """Login"""
        await super().login()
        return super().profile_id   # Once login succeeds we have a profile_id


    async def _async_logout(self):
        """Logout"""
        await super().logout()


    async def _async_poll_profile(self, profile_id:str):
        """
        Attempt to refresh the profile
        """
        profile_dict = await super().fetch_profile()

        await self._async_on_profile_change(profile_id, profile_dict)


    async def _async_poll_profile_devices(self, profile_id:str):
        """
        Fetch all gateways and all devices in a profile
        """
        old_device_ids = set(self.devices.keys())
        new_device_ids = set()

        # Fetch all gateways in this profile
        gateway_dicts = await super().fetch_gateways()

        for gateway_id,gateway_dict in gateway_dicts.items():
            await self._async_on_device_change(SmartWaterDataFamily.GATEWAY, gateway_id, gateway_dict)
            new_device_ids.add(gateway_id)

            # Fetch all devices for this gateway
            gw_device_dicts = await super().fetch_devices(gateway_id)

            for device_id,device_dict in gw_device_dicts.items():
                await self._async_on_device_change(SmartWaterDataFamily.DEVICE, device_id, device_dict)
                new_device_ids.add(device_id)

        # Cleanup - remove any old devices that we don't see anymore
        del_device_ids = old_device_ids - new_device_ids
        for id in del_device_ids:
            self.devices.pop(id, None)


    async def async_subscribe_to_push_data(self, device_configs: list[SmartWaterDeviceConfig], callback):
        """
        Subscribe to changes in profile. gateway and devices (tanks and pumps)
        """
        try:
            # Remember how to report back data changes to the coordinator
            self._async_data_listener = callback

            # Register listeners for changes in remote data
            await super().on_profile(self._on_profile_change)

            for device_config in device_configs:
                match device_config.family:
                    case SmartWaterDataFamily.GATEWAY: await super().on_gateway(device_config.id, self._on_gateway_change)
                    case SmartWaterDataFamily.DEVICE:  await super().on_device(device_config.id, self._on_device_change)

        except Exception as e:
            _LOGGER.info(f"{e}")


    def _on_profile_change(self, profile_id: str, profile_dict: dict):
        """
        AsyncSmartWaterApi.on_profile() needs a sync callback function.
        We jump back into the async event loop here.
        """
        self._hass.create_task(self._async_on_profile_change(profile_id, profile_dict))


    async def _async_on_profile_change(self, profile_id: str, profile_dict: dict):
        """Handle updated profile received from the remote servers"""
        try:
            context = {
                'username': self._username,
            }
            self.profile = SmartWaterData(family=SmartWaterDataFamily.PROFILE, id=profile_id, dict=profile_dict, context=context)

            _LOGGER.info(f"Received profile data for {self._username} ({profile_id})")

            # Signal to the coordinator that there were changes in the api data
            if self._async_data_listener is not None:
                await self._async_data_listener()

        except Exception as e:
            _LOGGER.info(f"{e}")


    def _on_gateway_change(self, gateway_id: str, gateway_dict: dict):
        """
        AsyncSmartWaterApi.on_gateway() needs a sync callback function.
        We jump back into the async event loop here.
        """
        self._hass.create_task(self._async_on_device_change(SmartWaterDataFamily.GATEWAY, gateway_id, gateway_dict))
        

    def _on_device_change(self, device_id: str, device_dict: dict):
        """
        AsyncSmartWaterApi.on_device() needs a sync callback function.
        We jump back into the async event loop here.
        """
        self._hass.create_task(self._async_on_device_change(SmartWaterDataFamily.DEVICE, device_id, device_dict))
        

    async def _async_on_device_change(self, device_family, device_id: str, device_dict: dict):
        """Handle updated device (gateway, tank or pump) received from the remote servers"""
        try:
            context = {
                "profile_id": super().profile_id,
            }
            device = SmartWaterData(family=device_family, id=device_id, dict=device_dict, context=context) 
        
            _LOGGER.info(f"Received device data for {device.name} ({device.id})")
            self.devices[device.id] = device

            # Signal to the coordinator that there were changes in the api data
            if self._async_data_listener is not None:
                await self._async_data_listener()

        except Exception as e:
            _LOGGER.info(f"{e}")


    async def async_get_diagnostics(self) -> dict[str, Any]:

        diag = await super().get_diagnostics()

        diag["data"].update( {
            "profile": self.profile.to_dict(),
            "devices": [ d.to_dict() for d in self.devices.values() ],
        } )
        return diag
   






