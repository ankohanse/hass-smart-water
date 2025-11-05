import logging

from dataclasses import asdict, dataclass
from enum import StrEnum
from jsonpath_ng import parse as jsonpath_parse
from typing import Any

from homeassistant.const import Platform

from smartwater import (
    SmartWaterDataError,
)

from .const import (
    PLATFORM_TO_PF,
)


# Define logger
_LOGGER = logging.getLogger(__name__)


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
    DP(fam="d",      key="serial",             name="Serial",               pf=None,  flag="",       path="serialNumber",            fmt="s",  unit="",     opt={}),
    DP(fam="d",      key="version",            name="Version",              pf=None,  flag="",       path="version",                 fmt="s",  unit="",     opt={}),
    DP(fam="d",      key="gateway_id",         name="Gateway Id",           pf=None,  flag="",       path="gatewayId",               fmt="s",  unit="",     opt={}),
    DP(fam="d",      key="status",             name="Status",               pf="sen", flag="e,none", path="status",                  fmt="s",  unit="",     opt={}),
    DP(fam="d",      key="alert_any",          name="Any Alerts",           pf="bin", flag="e,None", path="anyAlerts",               fmt="b",  unit="",     opt={}),

    # For Device.Tank
    DP(fam="d.tank", key="water_level",        name="Water Level",          pf="sen", flag="e,none", path="waterLevel",              fmt="i",  unit="%",    opt={}),
    DP(fam="d.tank", key="trend_level",        name="Trend Level",          pf="sen", flag="e,none", path="trendLevel",              fmt="e",  unit="",     opt={ "0": "flat", "1": "up", "-1": "down" } ),
    DP(fam="d.tank", key="days_remaining",     name="Days remaining",       pf="sen", flag="e,none", path="daysRemaining",           fmt="i",  unit="d",    opt={}),
    DP(fam="d.tank", key="avg_daily_use",      name="Avg Daily Use",        pf="sen", flag="e,none", path="avgDailyUse",             fmt="f2", unit="%",    opt={}),
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
    DP(fam="d.tank", key="days_number",        name="Days Number",          pf="sen", flag="d,diag", path="daysNumber",              fmt="i",  unit="d",    opt={}),
    DP(fam="d.tank", key="device_voltage",     name="Device Voltage",       pf="sen", flag="d,diag", path="devVoltage",              fmt="f2", unit="V",    opt={}),
    DP(fam="d.tank", key="sensor_status",      name="Sensor Status",        pf="sen", flag="d,diag", path="sensorStatus",            fmt="i",  unit="%",    opt={}),
    DP(fam="d.tank", key="last_report",        name="Last Report",          pf="sen", flag="d,diag", path="lastReport",              fmt="t",  unit="",     opt={}),
    DP(fam="d.tank", key="last_modified",      name="Last Modified",        pf="sen", flag="d,diag", path="lastModified",            fmt="t",  unit="",     opt={}),
    DP(fam="d.tank", key="alert_not_receiving",name="Not Receiving Alert",  pf="bin", flag="d,diag", path="alerts.notReceiving",     fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="alert_not_reporting",name="Not Reporting Alert",  pf="bin", flag="d,diag", path="alerts.notReporting",     fmt="b",  unit="",     opt={}),
    DP(fam="d.tank", key="adc_value",          name="Adc Value",            pf="sen", flag="d,diag", path="adcValue",                fmt="i",  unit="",     opt={}),
    DP(fam="d.tank", key="battery_adc",        name="Battery Adc",          pf="sen", flag="d,diag", path="batteryADC",              fmt="i",  unit="",     opt={}),
    DP(fam="d.tank", key="height",             name="Height",               pf="sen", flag="d,diag", path="settings.height",         fmt="f1", unit="m",    opt={}),
    DP(fam="d.tank", key="outflow_height",     name="Outflow Height",       pf="sen", flag="d,diag", path="settings.outflowHeight",  fmt="f1", unit="m",    opt={}),
    DP(fam="d.tank", key="replace_filter_at",  name="Replace Filter At",    pf="sen", flag="d,diag", path="settings.replaceFilterAt",fmt="t",  unit="",     opt={}),
    DP(fam="d.tank", key="clean_tank_at",      name="Clean Tank At",        pf="sen", flag="d,diag", path="settings.cleanTankAt",    fmt="t",  unit="",     opt={}),

    # For Device.Tank (not exposed, seem to have internal/unrelevant/never-changing values)
    DP(fam="d.tank", key="station_rssi",       name="Station RSSI",         pf=None,  flag="d,diag", path="stationRSSI",             fmt="i",  unit="dBm",  opt={}),
    DP(fam="d.tank", key="device_rssi",        name="Device RSSI",          pf=None,  flag="d,diag", path="deviceRSSI",              fmt="i",  unit="dBm",  opt={}),
    DP(fam="d.tank", key="min_level",          name="Min Level",            pf=None,  flag="d,diag", path="minLevel",                fmt="i",  unit="",     opt={}),
    DP(fam="d.tank", key="max_level",          name="Max Level",            pf=None,  flag="d,diag", path="maxLevel",                fmt="i",  unit="",     opt={}),
    DP(fam="d.tank", key="delta_percentage",   name="Delta Percentage",     pf=None,  flag="d,diag", path="deltaPercentage",         fmt="f2", unit="%",    opt={}),
    DP(fam="d.tank", key="clean_time",         name="Clean Time",           pf=None,  flag="d,diag", path="settings.cleanTime",      fmt="i",  unit="month",opt={}),
    DP(fam="d.tank", key="filter_time",        name="Filter Time",          pf=None,  flag="d,diag", path="settings.filterTime",     fmt="i",  unit="month",opt={}),
    DP(fam="d.tank", key="fluid_density",      name="Fluid Density",        pf=None,  flag="d,diag", path="settings.fluidDensity",   fmt="f2", unit="",     opt={}),
]

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
    ADDRESS = "address"
    GATEWAY_ID = "gatewayId"


class SmartWaterDatapoint(DP):
    def __init__(self, dp: DP):
        super().__init__(**asdict(dp))

        flag_parts = self.flag.split(',')

        self.flag_enabled  = flag_parts[0] if len(flag_parts) > 0 else ''
        self.flag_category = flag_parts[1] if len(flag_parts) > 1 else ''


class SmartWaterData:
    def __init__(self, family: SmartWaterDataFamily, id: str, data: dict[str,Any], context: dict[str,Any]):
        # Set initial values for all properties
        self.family = family
        self.family_sub = family  # Must get initial value before any get_value lookups below
        self.id = id
        self.name = id

        self._data = data
        self._context = context

        # Get derived properties; this may overwrite earlier initial valeus
        sub = self.get_value(SmartWaterDataKey.TYPE)
        name = self.get_value(SmartWaterDataKey.NAME)

        self.family_sub = f"{family}.{sub}" if sub is not None else family
        self.name = name or sub or id

            
    def get_datapoints_for_platform(self, target_platform: str) -> list[SmartWaterDatapoint]:

        # Get abbreviated platform str matching the target platform
        pf:str = PLATFORM_TO_PF.get(target_platform, None)
        if pf is None:
            _LOGGER.warning(f"Trying to get abbreviated platform for '{target_platform}. Please contact the developer of this integration.")
            return []

        # Collect all datapoints associated with this device family and for this platform 
        return [ SmartWaterDatapoint(dp) for dp in DATAPOINTS if dp.pf==pf and self.family_sub.startswith(dp.fam) ]


    def get_datapoint(self, key: SmartWaterDataKey|str) -> SmartWaterDatapoint:
        for dp in DATAPOINTS:
            if dp.key == key and self.family_sub.startswith(dp.fam):
                return SmartWaterDatapoint(dp)

        return None


    def get_value(self, key: SmartWaterDataKey|str) -> Any:

        # get datapoint that defines properties for this key within this family
        datapoint = self.get_datapoint(key)
        if datapoint is None:
            return None
        if datapoint.path is None:
            return None

        # Apply pre-defined paths
        profile_id = self._context.get("profile_id", "")

        match datapoint.path:
            case '#canEdit': path = f"members.{profile_id}.canEdit"
            case '#enabled': path = f"members.{profile_id}.enabled"
            case _:          path = datapoint.path

        # Lookup the value for this datapoint
        try:
            match = jsonpath_parse(path).find(self._data)

            match len(match):
                case 1: return match[0].value
                case 0: return None
                case _: _LOGGER.debug(f"Error while resolving {path}: {len(match)} items found")
        
        except Exception as ex:
            _LOGGER.debug(f"Error while resolving {path}: {str(ex)}")

        return None
        

    def to_dict(self):
        return {
            "family": self.family,
            "family_sub": self.family_sub,
            "id": self.id,
            "name": self.name,
            "data": self._data,
            "context": self._context
        }


    @staticmethod
    def from_dict(d: dict[str,Any]) -> 'SmartWaterData':
        family  = d.get("family", None)
        id      = d.get("id", None)
        data    = d.get("data", None)
        context = d.get("context", {})

        if family is None or id is None or data is None:
            raise SmartWaterDataError()
        
        return SmartWaterData(family, id, data, context)

        