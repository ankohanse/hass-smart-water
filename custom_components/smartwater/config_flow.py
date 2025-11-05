"""config_flow.py: Config flow for DAB Pumps integration."""
from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant import config_entries, exceptions

from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.exceptions import IntegrationError
from homeassistant.helpers.selector import selector

from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
)

from smartwater import (
    SmartWaterError,
    SmartWaterAuthError,
) 


from .const import (
    DOMAIN,
    DEFAULT_USERNAME,
    DEFAULT_PASSWORD,
    CONF_PROFILE_ID,
    CONF_PROFILE_NAME,
)

from .coordinator import (
    SmartWaterCoordinatorFactory,
    SmartWaterCoordinator,
)

_LOGGER = logging.getLogger(__name__)

# internal consts only used in config flow
CONF_ROLE_MENU = "role_menu"

@config_entries.HANDLERS.register("smartwater")
class ConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""
    
    VERSION = 1
    
    def __init__(self):
        """Initialize config flow."""
        self._username = None
        self._password = None
        self._profile = None
        self._errors = {}

        # Assign the HA configured log level of this module to the aioSmartWater module
        log_level: int = _LOGGER.getEffectiveLevel()
        lib_logger: logging.Logger = logging.getLogger("smartwater")
        lib_logger.setLevel(log_level)

        _LOGGER.info(f"Logging at {logging.getLevelName(log_level)}")
    
    
    async def async_try_connection(self):
        """Test the username and password by connecting to the Smart Water servers"""
        _LOGGER.info("Trying connection...")
        
        self._errors = {}
        coordinator = SmartWaterCoordinatorFactory.create_temp(self._username, self._password)
        try:
            # Call the SmartWaterApi with the detect_device method
            self._profile = await coordinator.async_config_flow_data()
            
            if self._profile is not None:
                _LOGGER.info("Successfully connected!")
                _LOGGER.debug(f"profile {self._profile.id}: {self._profile._data}")
                self._errors = {}
                return True
            else:
                self._errors[CONF_USERNAME] = f"No profile detected"
        
        except SmartWaterError as e:
            self._errors[CONF_PASSWORD] = f"Failed to connect to Smart Water servers"
        except SmartWaterAuthError as e:
            self._errors[CONF_PASSWORD] = f"Authentication failed"
        except Exception as e:
            self._errors[CONF_PASSWORD] = f"Unknown error: {e}"

        finally:
            await SmartWaterCoordinatorFactory.async_close_temp(coordinator)
        
        return False
    

    # This is step 1 for the user/pass function.
    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle a flow initialized by the user."""
        
        if user_input is not None:
            _LOGGER.debug(f"Step user - handle input {user_input}")
            
            self._username = user_input.get(CONF_USERNAME, '')
            self._password = user_input.get(CONF_PASSWORD, '')
            
            # test the username+password and retrieve the profile for this user
            await self.async_try_connection()
            
            if not self._errors:
                # go to the second step to choose which profile to use
                return await self.async_step_finish()
        
        # Show the form with the username+password
        _LOGGER.debug(f"Step user - show form")
        
        return self.async_show_form(
            step_id = "user", 
            data_schema = vol.Schema({
                vol.Required(CONF_USERNAME, description={"suggested_value": self._username or DEFAULT_USERNAME}): str,
                vol.Required(CONF_PASSWORD, description={"suggested_value": self._password or DEFAULT_PASSWORD}): str,
            }),
            errors = self._errors
        )
    
    
    async def async_step_finish(self, user_input=None) -> FlowResult:
        """Configuration has finished"""
        
        # Use profile_id as unique_id for this config flow to avoid the same hub being setup twice
        await self.async_set_unique_id(self._profile.id)
        self._abort_if_unique_id_configured()
    
        # Create the integration entry
        return self.async_create_entry(
            title = self._profile.name, 
            data = {
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_PROFILE_ID: self._profile.id,
                CONF_PROFILE_NAME: self._profile.name,
            },
            options = {
            }
        )
    
