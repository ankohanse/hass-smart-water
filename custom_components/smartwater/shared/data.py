"""
Data definitions for Smart Water and Gallagher Water integrations.

Note that this file is shared as is between the two integrations. 
Do not place code that is specific to only one of these integration in here!
"""
import logging

from dataclasses import asdict, dataclass
from enum import StrEnum
from jsonata import Jsonata
from typing import Any

from homeassistant.const import Platform


# Define logger
_LOGGER = logging.getLogger(__name__)


OPT_TREND_LEVEL = {
    '0':'flat',
    '1':'up', '2':'up', '3':'up', '4':'up', '5':'up',
    '-1': 'down', '-2':'down', '-3':'down', '-4':'down', '-5': 'down',
}


# Map platform to pf codes for both enabled and disabled entities
PLATFORM_TO_PF: dict[Platform, str] = {
    Platform.SENSOR:        "sen",
    Platform.BINARY_SENSOR: "bin",
}
PLATFORMS = list(PLATFORM_TO_PF.keys())


@dataclass
class DP:
    fam: str            # Device Family  
    key: str            # Datapoint unique key
    name: str           # Friendly name
    pf: str             # Target platform abbreviation; Sensor, Binary_Sensor etc. If None then not added as entity but may be used internally
    flag: str           # Comma separated flags: enabled/disabled (e or d), entity category (conf, diag or none) 
    path: str           # Path for value within responses from remote server
    fmt: type           # Data format (s=str, b=bool, i=int, t=timestamp, f[n]=float with precision)
    unit: str           # Data unit of measurement
    opt: dict[str,Any]  # Options for Enums

DATAPOINTS = [
    # These are shared over all device families, although not all entities will be applicable to all families
    DP(fam="",       key="name",               name="Name",                 pf=None,  flag="",       path="name",                    fmt="s",  unit="",     opt={}),
    DP(fam="",       key="type",               name="Type",                 pf=None,  flag="",       path="type",                    fmt="s",  unit="",     opt={}),

    # For Profile
    DP(fam="pr",     key="account_type",       name="Account Type",         pf=None,  flag="",       path="accountConfig.type",      fmt="s",  unit="",     opt={}),

    # For Gateway
    DP(fam="gw",     key="can_edit",           name="Can Edit",             pf=None,  flag="",       path="#canEdit",                fmt="b",  unit="",     opt={}),
    DP(fam="gw",     key="enabled",            name="Enabled",              pf=None,  flag="",       path="#enabled",                fmt="b",  unit="",     opt={}),
    DP(fam="gw",     key="status",             name="Status",               pf="sen", flag="e,none", path="status",                  fmt="s",  unit="",     opt={}),
    DP(fam="gw",     key="alert_any",          name="Any Alerts",           pf="bin", flag="e,none", path="anyAlerts",               fmt="b",  unit="",     opt={}),
    DP(fam="gw",     key="signal",             name="Signal",               pf="sen", flag="e,none", path="signalStrength",          fmt="i",  unit="dB",   opt={}),

    # For Gateway (default disabled entity)
    DP(fam="gw",     key="address",            name="Location Address",     pf="sen", flag="d,diag", path="location.address",        fmt="s",  unit="",     opt={}),
    DP(fam="gw",     key="postcode",           name="Location Postcode",    pf="sen", flag="d,diag", path="location.postcode",       fmt="s",  unit="",     opt={}),
    DP(fam="gw",     key="suburb",             name="Location Suburb",      pf="sen", flag="d,diag", path="location.suburb",         fmt="s",  unit="",     opt={}),
    DP(fam="gw",     key="city",               name="Location City",        pf="sen", flag="d,diag", path="location.city",           fmt="s",  unit="",     opt={}),
    DP(fam="gw",     key="country",            name="Location Country",     pf="sen", flag="d,diag", path="location.country",        fmt="s",  unit="",     opt={}),
    DP(fam="gw",     key="longitude",          name="Location Longitude",   pf="sen", flag="d,diag", path="location.lat",            fmt="f4", unit="",     opt={}),
    DP(fam="gw",     key="latitude",           name="Location Latitude",    pf="sen", flag="d,diag", path="location.lng",            fmt="f4", unit="",     opt={}),

    # For Gateway (not exposed, seem to have internal/unrelevant values)
    DP(fam="gw",     key="use_v2_resync",      name="Use V2 Resync",        pf=None,  flag="d,diag", path="useV2Resync",             fmt="b",  unit="",     opt={}),

    # For Device (generic)
    DP(fam="d",      key="name",               name="Name",                 pf=None,  flag="",       path="settings.name",           fmt="s",  unit="",     opt={}),
    DP(fam="d",      key="serial",             name="Serial",               pf=None,  flag="",       path="serialNumber",            fmt="s",  unit="",     opt={}),
    DP(fam="d",      key="version",            name="Version",              pf=None,  flag="",       path="version",                 fmt="s",  unit="",     opt={}),
    DP(fam="d",      key="gateway_id",         name="Gateway Id",           pf=None,  flag="",       path="gatewayId",               fmt="s",  unit="",     opt={}),
    DP(fam="d",      key="status",             name="Status",               pf="sen", flag="e,none", path="status",                  fmt="s",  unit="",     opt={}),
    DP(fam="d",      key="alert_any",          name="Any Alerts",           pf="bin", flag="e,None", path="anyAlerts",               fmt="b",  unit="",     opt={}),

    # For Device.Tank
    DP(fam="d.tank", key="water_level",        name="Water Level",          pf="sen", flag="e,none", path="waterLevel",              fmt="i",  unit="%",    opt={}),
    DP(fam="d.tank", key="water_height",       name="Water Height",         pf="sen", flag="e,none", path="#waterHeight",            fmt="f2", unit="m",    opt={}),
    DP(fam="d.tank", key="trend_level",        name="Trend Level",          pf="sen", flag="e,none", path="trendLevel",              fmt="e",  unit="",     opt=OPT_TREND_LEVEL),
    DP(fam="d.tank", key="days_remaining",     name="Days remaining",       pf="sen", flag="e,none", path="daysRemaining",           fmt="i",  unit="d",    opt={}),
    DP(fam="d.tank", key="avg_daily_use",      name="Avg Daily Use",        pf="sen", flag="e,none", path="avgDailyUse",             fmt="f1", unit="%",    opt={}),
    DP(fam="d.tank", key="battery_level",      name="Battery Level",        pf="sen", flag="e,diag", path="batteryLevel",            fmt="i",  unit="%",    opt={}),
    DP(fam="d.tank", key="alert_level_low",    name="Low Level Alert",      pf="bin", flag="e,diag", path="alerts.lowLevelAlert",    fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="alert_level_high",   name="High Level Alert",     pf="bin", flag="e,diag", path="alerts.highLevelAlert",   fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="alert_days_low",     name="Days Remaining Alert", pf="bin", flag="e,diag", path="alerts.daysRemainingLow", fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="alert_battery_low",  name="Battery Low Alert",    pf="bin", flag="e,diag", path="alerts.batteryLow",       fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="alert_filter",       name="Filter Alert",         pf="bin", flag="e,diag", path="alerts.filter",           fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="alert_clean_tank",   name="Clean Tank Alert",     pf="bin", flag="e,diag", path="alerts.cleanTank",        fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="alert_usage",        name="Abnormal Usage Alert", pf="bin", flag="e,diag", path="alerts.usageAbnormal",    fmt="b",  unit="",     opt={}),

    # For Device.Tank (default disabled entity)
    DP(fam="d.tank", key="device_number",      name="Device Number",        pf="sen", flag="d,diag", path="deviceNumber",            fmt="s",  unit="",     opt={}),
    DP(fam="d.tank", key="aux_power",          name="Aux Power",            pf="bin", flag="d,diag", path="auxPower",                fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="device_voltage",     name="Device Voltage",       pf="sen", flag="d,diag", path="devVoltage",              fmt="f2", unit="V",    opt={}),
    DP(fam="d.tank", key="sensor_status",      name="Sensor Status",        pf="sen", flag="d,diag", path="sensorStatus",            fmt="i",  unit="%",    opt={}),
    DP(fam="d.tank", key="last_report",        name="Last Report",          pf="sen", flag="d,diag", path="lastReport",              fmt="t",  unit="",     opt={}),
    DP(fam="d.tank", key="alert_not_receiving",name="Not Receiving Alert",  pf="bin", flag="d,diag", path="alerts.notReceiving",     fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="alert_not_reporting",name="Not Reporting Alert",  pf="bin", flag="d,diag", path="alerts.notReporting",     fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="tank_height",        name="Tank Height",          pf="sen", flag="d,diag", path="settings.height",         fmt="f1", unit="m",    opt={}),
    DP(fam="d.tank", key="outflow_height",     name="Outflow Height",       pf="sen", flag="d,diag", path="settings.outflowHeight",  fmt="f1", unit="m",    opt={}),
    DP(fam="d.tank", key="replace_filter_at",  name="Replace Filter At",    pf="sen", flag="d,diag", path="settings.replaceFilterAt",fmt="t",  unit="",     opt={}),
    DP(fam="d.tank", key="clean_tank_at",      name="Clean Tank At",        pf="sen", flag="d,diag", path="settings.cleanTankAt",    fmt="t",  unit="",     opt={}),

    # For Device.Tank (not exposed, seem to have internal/unrelevant/never-changing values)
    DP(fam="d.tank", key="last_modified",      name="Last Modified",        pf=None,  flag="d,diag", path="lastModified",            fmt="t",  unit="",     opt={}),
    DP(fam="d.tank", key="station_rssi",       name="Station RSSI",         pf=None,  flag="d,diag", path="stationRSSI",             fmt="i",  unit="dBm",  opt={}),
    DP(fam="d.tank", key="device_rssi",        name="Device RSSI",          pf=None,  flag="d,diag", path="deviceRSSI",              fmt="i",  unit="dBm",  opt={}),
    DP(fam="d.tank", key="min_level",          name="Min Level",            pf=None,  flag="d,diag", path="minLevel",                fmt="i",  unit="",     opt={}),
    DP(fam="d.tank", key="max_level",          name="Max Level",            pf=None,  flag="d,diag", path="maxLevel",                fmt="i",  unit="",     opt={}),
    DP(fam="d.tank", key="days_number",        name="Days Number",          pf=None,  flag="d,diag", path="daysNumber",              fmt="i",  unit="d",    opt={}),
    DP(fam="d.tank", key="delta_percentage",   name="Delta Percentage",     pf=None,  flag="d,diag", path="deltaPercentage",         fmt="f2", unit="%",    opt={}),
    DP(fam="d.tank", key="clean_time",         name="Clean Time",           pf=None,  flag="d,diag", path="settings.cleanTime",      fmt="i",  unit="month",opt={}),
    DP(fam="d.tank", key="filter_time",        name="Filter Time",          pf=None,  flag="d,diag", path="settings.filterTime",     fmt="i",  unit="month",opt={}),
    DP(fam="d.tank", key="fluid_density",      name="Fluid Density",        pf=None,  flag="d,diag", path="settings.fluidDensity",   fmt="f2", unit="",     opt={}),
    DP(fam="d.tank", key="adc_value",          name="Adc Value",            pf=None,  flag="d,diag", path="adcValue",                fmt="i",  unit="",     opt={}),
    DP(fam="d.tank", key="battery_adc",        name="Battery Adc",          pf=None,  flag="d,diag", path="batteryADC",              fmt="i",  unit="",     opt={}),

    # For Device.Pump
    DP(fam="d.pump", key="started_at",         name="Started At",                pf="sen", flag="e,diag", path="startedAt",                        fmt="t",  unit="",     opt={}),
    DP(fam="d.pump", key="alert_start_blocked",name="Auto Start Blocked Alert",  pf="bin", flag="e,diag", path="alerts.autoStartBlocked",          fmt="b",  unit="",     opt={}),
    DP(fam="d.pump", key="alert_forced_stop",  name="Forced Stop Alert",         pf="bin", flag="e,diag", path="alerts.forcedStop",                fmt="b",  unit="",     opt={}),
    DP(fam="d.pump", key="alert_days_low",     name="Communication Error Alert", pf="bin", flag="e,diag", path="alerts.communicationError",        fmt="b",  unit="",     opt={}),
    DP(fam="d.pump", key="leak_warning",       name="Leak Warning Alert",        pf="bin", flag="e,diag", path="alerts.leakWarning",               fmt="b",  unit="",     opt={}),

    # For Device.Pump (default disabled entity)
    DP(fam="d.pump", key="device_number",      name="Device Number",             pf="sen", flag="d,diag", path="deviceNumber",            fmt="s",  unit="",     opt={}),
    DP(fam="d.pump", key="pump_mode",          name="Pump Mode",                 pf="sen", flag="d,diag", path="settings.pumpMode",                fmt="s",  unit="",    opt={}),
    DP(fam="d.pump", key="src",                name="Source Tank",               pf="sen", flag="d,diag", path="settings.sourceTank",              fmt="s",  unit="",    opt={}),
    DP(fam="d.pump", key="dst",                name="Destination Tank",          pf="sen", flag="d,diag", path="settings.destinationTank",         fmt="s",  unit="",    opt={}),
    DP(fam="d.pump", key="src_stop_time_from", name="Source Stop Time From",     pf="sen", flag="d,diag", path="settings.sourceTankStopTimeFrom",  fmt="i",  unit="",    opt={}),
    DP(fam="d.pump", key="src_stop_time_to",   name="Source Stop Time To",       pf="sen", flag="d,diag", path="settings.sourceTankStopTimeTo",    fmt="i",  unit="",    opt={}),
    DP(fam="d.pump", key="src_stop_level",     name="Source Stop Level",         pf="sen", flag="d,diag", path="settings.sourceTankStopLevel",     fmt="i",  unit="%",   opt={}),
    DP(fam="d.pump", key="dst_stop_level",     name="Destination Stop Level",    pf="sen", flag="d,diag", path="settings.destinationTankStopLevel",fmt="i",  unit="%",   opt={}),
    DP(fam="d.pump", key="dst_start_level",    name="Destination Start Level",   pf="sen", flag="d,diag", path="settings.pumpAutoStartLevel",      fmt="i",  unit="%",   opt={}),
    DP(fam="d.pump", key="pump_runtime",       name="Pump Run Time",             pf="sen", flag="d,diag", path="settings.pumpRuntime",             fmt="i",  unit="",    opt={}),

    # For Device.Pump (not exposed, seem to have internal/unrelevant/never-changing values)
    DP(fam="d.pump", key="signal_level",       name="Signal Level",              pf=None,  flag="d,diag", path="signalLevel",                      fmt="t",  unit="",     opt={}),
]

DATAPATHS_EXTRA = {
    '#canEdit':     "$lookup(members, context.profile_id).canEdit",
    '#enabled':     "$lookup(members, context.profile_id).enabled",
    '#waterHeight': "settings.height * waterLevel / 100.0",
}

class SmartWaterDataFamily(StrEnum):
    PROFILE = "pr"
    GATEWAY = "gw"
    DEVICE = "d"
    PUMP = "d.pump"
    TANK = "d.tank"

class SmartWaterDataKey(StrEnum):
    # Standard items
    NAME = "name"
    TYPE = "type"
    SERIAL = "serial"
    VERSION = "version"
    GATEWAY_ID = "gateway_id"
    DEVICE_NUMBER = "device_number"


class SmartWaterDatapoint(DP):
    def __init__(self, dp: DP):
        super().__init__(**asdict(dp))

        # Resolve path if needed
        if self.path.startswith('#'):
            self.path = DATAPATHS_EXTRA.get(self.path)
        
        # Resolve flags
        flag_parts = self.flag.split(',')

        self.flag_enabled  = flag_parts[0] if len(flag_parts) > 0 else ''
        self.flag_category = flag_parts[1] if len(flag_parts) > 1 else ''


    @staticmethod
    def for_family_and_key(family_sub: str, key: str) -> 'SmartWaterDatapoint':

        # Loop over reversed list to make sure we use the longest family_sub match
        return next( (SmartWaterDatapoint(dp) for dp in reversed(DATAPOINTS) if family_sub.startswith(dp.fam) and dp.key==key), None )


    @staticmethod
    def for_family_and_platform(family_sub: str, target_platform: str) -> list['SmartWaterDatapoint']:

        # Get abbreviated platform str matching the target platform
        pf:str = PLATFORM_TO_PF.get(target_platform, None)
        if pf is None:
            _LOGGER.warning(f"Trying to get abbreviated platform for '{target_platform}. Please contact the developer of this integration.")
            return []

        # Collect all datapoints associated with this device family and for this platform 
        return [ SmartWaterDatapoint(dp) for dp in DATAPOINTS if family_sub.startswith(dp.fam) and dp.pf==pf  ]



class SmartWaterData:
    def __init__(self, family: SmartWaterDataFamily, id: str, dict: dict[str,Any]=None, context: dict[str,Any]=None):
        # Set initial values for all properties
        self._family = family
        self._id = id
        self._name = None
        self._type = None
        self._device_number = None
        
        self._dict = dict
        if context is not None:
            self._dict = self._dict | { 'context': context }

        # Get derived properties from dict; this may overwrite earlier initial values
        self._name = self.get_value(SmartWaterDataKey.NAME)
        self._type = self.get_value(SmartWaterDataKey.TYPE)
        self._device_number = self.get_value(SmartWaterDataKey.DEVICE_NUMBER)


    @property
    def family(self):
        return self._family
    
    @property
    def family_sub(self):
        return f"{self.family}.{self.type}" if self.type is not None else self.family
    
    @property
    def id(self):
        return self._id
            
    @property
    def name(self):
        if self._name:
            return self._name
        
        elif self._type and self._device_number:
            return f"{self._type} {self._device_number}"
        
        elif self._type and self._family in [SmartWaterDataFamily.GATEWAY]:
            return self._type
        
        else:
            return self._id
    
    @property
    def type(self):
        return self._type
            
            
    def get_value(self, key: SmartWaterDataKey|str) -> Any:

        # get datapoint that defines properties for this key within this family
        datapoint = SmartWaterDatapoint.for_family_and_key(self.family_sub, key)
        if datapoint is None:
            return None
        if self._dict is None:
            return None

        try:
            # Lookup the value for this datapoint
            return Jsonata(datapoint.path).evaluate(self._dict)
        
        except Exception as ex:
            _LOGGER.debug(f"Could not resolve path {datapoint.path} for {key}: {str(ex)}")

        return None
        

    def to_dict(self):
        return {
            "family": self.family,
            "id": self.id,
            "name": self.name,
            "dict": self._dict
        }


@dataclass
class SmartWaterDeviceConfig():

    family: str
    family_sub: str
    id: str
    name: str
    type: str
    serial: str
    version: str
    device_number: str
    gateway_id: str


    @staticmethod
    def from_data(data: SmartWaterData):
        return SmartWaterDeviceConfig(
            family = data.family,
            family_sub = data.family_sub,
            id = data.id,
            name = data.name,
            type = data.type,
            serial = data.get_value(SmartWaterDataKey.SERIAL) or data.id,
            version = data.get_value(SmartWaterDataKey.VERSION),
            device_number = data.get_value(SmartWaterDataKey.DEVICE_NUMBER),
            gateway_id = data.get_value(SmartWaterDataKey.GATEWAY_ID)
        )    
            

    def get_datapoints_for_platform(self, target_platform: str) -> list[SmartWaterDatapoint]:
        return SmartWaterDatapoint.for_family_and_platform(self.family_sub, target_platform)


    def get_datapoint(self, key: SmartWaterDataKey|str) -> SmartWaterDatapoint:
        return SmartWaterDatapoint.for_family_and_key(self.family_sub, key)


    def to_dict(self):
        """Create a dict representing the values in the SmartWaterDeviceConfig object"""
        result = {
            "family": self.family,
            "family_sub": self.family_sub,
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "serial": self.serial,
            "version": self.version,
            "device_number": self.device_number,
            "gateway_id": self.gateway_id,
        }
        return {k:v for k,v in result.items() if v is not None}


    @staticmethod
    def from_dict(d: dict[str,Any]) -> 'SmartWaterDeviceConfig':
        """Construct a new SmartWaterDeviceConfig object from a dict"""
        return SmartWaterDeviceConfig(
            family        = d.get("family", ""),
            family_sub    = d.get("family_sub", ""),
            id            = d.get("id", None),
            name          = d.get("name", None),
            type          = d.get("type", None),
            serial        = d.get("serial", None),
            version       = d.get("version", None),
            device_number = d.get("device_number", None),
            gateway_id    = d.get("gateway_id", None),
        )
