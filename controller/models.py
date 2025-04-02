"""Data models for BrewPi controller."""

from enum import Enum
from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field, validator


class ControllerMode(str, Enum):
    """Controller operation modes."""
    
    BEER_CONSTANT = "b"
    FRIDGE_CONSTANT = "f"
    PROFILE = "p"
    OFF = "o"


class DeviceFunction(int, Enum):
    """Device functions matching the firmware enum."""
    
    DEVICE_NONE = 0
    DEVICE_CHAMBER_DOOR = 1
    DEVICE_CHAMBER_HEAT = 2
    DEVICE_CHAMBER_COOL = 3
    DEVICE_CHAMBER_LIGHT = 4
    DEVICE_CHAMBER_TEMP = 5
    DEVICE_CHAMBER_ROOM_TEMP = 6
    DEVICE_CHAMBER_FAN = 7
    DEVICE_CHAMBER_RESERVED1 = 8
    DEVICE_BEER_TEMP = 9
    DEVICE_BEER_TEMP2 = 10
    DEVICE_BEER_HEAT = 11
    DEVICE_BEER_COOL = 12
    DEVICE_BEER_SG = 13
    DEVICE_BEER_RESERVED1 = 14
    DEVICE_BEER_RESERVED2 = 15
    DEVICE_MAX = 16


class DeviceHardware(int, Enum):
    """Device hardware types matching the firmware enum."""
    
    DEVICE_HARDWARE_NONE = 0
    DEVICE_HARDWARE_PIN = 1
    DEVICE_HARDWARE_ONEWIRE_TEMP = 2
    DEVICE_HARDWARE_ONEWIRE_2413 = 3
    # Skip 4 as mentioned in the comment
    DEVICE_HARDWARE_BLUETOOTH_INKBIRD = 5
    DEVICE_HARDWARE_BLUETOOTH_TILT = 6
    DEVICE_HARDWARE_TPLINK_SWITCH = 7


class Device(BaseModel):
    """BrewPi device (sensor/actuator) matching the C++ DeviceDefinition struct."""
    
    id: int = -1
    chamber: int = 0
    beer: int = 0
    deviceFunction: int = 0
    deviceHardware: int = 0
    pinNr: int = 0
    invert: int = 0
    pio: int = 0
    deactivate: int = 0
    calibrationAdjust: int = 0
    address: Optional[List[int]] = None
    value: Optional[float] = None  # Not in the C++ struct
    
    # Map int values to enums for convenience
    @property
    def function_enum(self) -> DeviceFunction:
        try:
            return DeviceFunction(self.deviceFunction)
        except ValueError:
            return DeviceFunction.DEVICE_NONE
            
    @property
    def hardware_enum(self) -> DeviceHardware:
        try:
            return DeviceHardware(self.deviceHardware)
        except ValueError:
            return DeviceHardware.DEVICE_HARDWARE_NONE


class DeviceListItem(BaseModel):
    """Item in the device list response from controller using the exact JSON keys.
    
    As defined in DeviceDefinitionKeys namespace in the firmware:
    - i: index
    - c: chamber
    - b: beer
    - f: function
    - h: hardware
    - p: pin
    - x: invert
    - d: deactivated
    - a: address (optional)
    - n: child_id or pio (optional)
    - j: calibrateadjust (optional)
    """
    
    i: int  # index (id)
    c: int  # chamber
    b: int  # beer
    f: int  # function
    h: int  # hardware
    p: int  # pin
    x: int = 0  # invert
    d: int = 0  # deactivated
    a: Optional[List[int]] = None  # address (optional)
    n: Optional[int] = None  # child_id or pio (optional)
    j: Optional[int] = None  # calibrateadjust (optional)
    
    # Additional fields not part of the core definition
    v: Optional[float] = None  # value (for sensors)
    w: Optional[int] = None  # write value (for actuators)


class ControlSettings(BaseModel):
    """Controller settings.
    
    This model matches the exact keys/values received from the controller and used in the 
    full config endpoint with "cs" key. The attribute names use camelCase as expected by Fermentrack.
    """
    
    mode: ControllerMode
    beerSet: float = 0.0
    fridgeSet: float = 0.0
    heatEst: float = 0.0  # Heat estimator
    coolEst: float = 0.0  # Cool estimator
    
    class Config:
        """Pydantic configuration."""
        populate_by_name = True


class ControlConstants(BaseModel):
    """Controller constants.
    
    This model matches the exact keys/values received from the controller and used in the
    full config endpoint with "cc" key. The attribute names use camelCase as expected by Fermentrack.
    
    Field names follow the exact format from the example:
    "tempFormat":"C","tempSetMin":1,"tempSetMax":30,"pidMax":10,"Kp":5,"Ki":0.25,"Kd":1.5,"iMaxErr":0.5,
    "idleRangeH":1,"idleRangeL":1,"heatTargetH":0.299,"heatTargetL":0.199,"coolTargetH":0.199,
    "coolTargetL":0.299,"maxHeatTimeForEst":600,"maxCoolTimeForEst":1200,"fridgeFastFilt":1,
    "fridgeSlowFilt":4,"fridgeSlopeFilt":3,"beerFastFilt":3,"beerSlowFilt":4,"beerSlopeFilt":4,"lah":0,"hs":0
    """
    
    # Temperature settings
    tempFormat: str = "C"
    tempSetMin: float = 1.0
    tempSetMax: float = 30.0
    
    # PID control parameters
    pidMax: float = 10.0
    Kp: float = 5.0
    Ki: float = 0.25
    Kd: float = 1.5
    iMaxErr: float = 0.5
    
    # Control ranges
    idleRangeH: float = 1.0
    idleRangeL: float = 1.0
    heatTargetH: float = 0.299
    heatTargetL: float = 0.199
    coolTargetH: float = 0.199
    coolTargetL: float = 0.299
    
    # Time estimation
    maxHeatTimeForEst: int = 600
    maxCoolTimeForEst: int = 1200
    
    # Filter settings
    fridgeFastFilt: int = 1
    fridgeSlowFilt: int = 4
    fridgeSlopeFilt: int = 3
    beerFastFilt: int = 3
    beerSlowFilt: int = 4
    beerSlopeFilt: int = 4
    
    # Hardware settings
    # NOTE - lah and hs are sent as booleans from Fermentrack, but are sent as/expected to be integers in the controller
    lah: int = 0  # Light as heater
    hs: int = 0   # Heating shared
    
    class Config:
        """Pydantic configuration."""
        populate_by_name = True


class MinimumTime(BaseModel):
    """Minimum time settings."""
    
    min_cool_time: int = Field(300, alias="minCoolTime")
    min_cool_idle_time: int = Field(300, alias="minCoolIdleTime")
    min_heat_time: int = Field(300, alias="minHeatTime")
    min_heat_idle_time: int = Field(300, alias="minHeatIdleTime")
    min_idle_time: int = Field(300, alias="minIdleTime")


class TemperatureData(BaseModel):
    """Temperature data from controller."""
    
    beer_temp: Optional[float] = Field(None, alias="beerTemp")
    beer_set: float = Field(0.0, alias="beerSet")
    fridge_temp: Optional[float] = Field(None, alias="fridgeTemp")
    fridge_set: float = Field(0.0, alias="fridgeSet")
    room_temp: Optional[float] = Field(None, alias="roomTemp")


class ControllerStatus(BaseModel):
    """Controller status for API.
    
    Matches the format used in the C++ implementation:
    ```
    doc["lcd"] = lcd;
    doc["temps"] = temps;
    doc["temp_format"] = String(tempControl.cc.tempFormat);
    doc["mode"] = String(tempControl.cs.mode);
    ```
    
    Note: The lcd field is a list of strings, as it's received directly from the controller.
    Each string represents a line on the LCD display.
    """
    lcd: List[str]  # LCD content as a list of strings (one per line)
    temps: Dict[str, Optional[float]]  # Temperature readings
    temp_format: str  # Temperature format (C or F)
    mode: str  # Controller mode


class MessageStatus(BaseModel):
    """Message flags for communication with Fermentrack."""

    # Device control messages
    restart_device: bool = False
    reset_eeprom: bool = False
    reset_connection: bool = False

    # Device update messages
    updated_cc: bool = False
    updated_cs: bool = False
    updated_mt: bool = False  # Not processed in this app currently - May be something to add for ESP32-S2 later
    updated_devices: Any = False

    refresh_config: bool = False

    # Default setting messages
    default_cc: bool = False
    default_cs: bool = False

    class Config:
        """Pydantic configuration."""
        populate_by_name = True


class SerializedDevice(BaseModel):
    """Device for API serialization in the compact format expected by Fermentrack.
    
    These fields directly match the firmware JSON keys for DeviceDefinition:
    i: index (id)
    c: chamber
    b: beer
    f: function
    h: hardware
    p: pin
    x: invert
    d: deactivated
    a: address (optional)
    n: child_id or pio (optional)
    j: calibrateadjust (optional)
    v: value (optional)
    w: write value (optional)
    """
    
    i: int  # index (id) 
    c: int  # chamber
    b: int  # beer
    f: int  # function
    h: int  # hardware type
    p: int  # pin
    x: int = 0  # invert
    d: int = 0  # deactivated
    a: Optional[List[int]] = None  # address (for OneWire devices)
    n: Optional[int] = None  # child_id or pio
    j: Optional[int] = None  # calibration adjust
    r: Optional[str] = None  # alias (name/role)
    
    # Runtime values that aren't part of the definition
    v: Optional[float] = None  # sensor value
    w: Optional[int] = None  # write value for actuators
    
    class Config:
        """Pydantic configuration."""
        populate_by_name = True

    @classmethod
    def from_device(cls, device: Device) -> 'SerializedDevice':
        """Convert Device to SerializedDevice in the compact format that matches C++ implementation."""
        return cls(
            i=device.id,
            c=device.chamber,
            b=device.beer,
            f=device.deviceFunction,
            h=device.deviceHardware,
            p=device.pinNr,
            x=device.invert,
            d=device.deactivate,
            a=device.address,
            n=device.pio,
            j=device.calibrationAdjust,
            r=f"Device {device.id}",  # Default name
            v=device.value
        )


class FullConfig(BaseModel):
    """Full controller configuration in Fermentrack format."""
    
    cs: ControlSettings  # Control settings
    cc: ControlConstants  # Control constants
    devices: List[SerializedDevice]  # Device list
    deviceID: str  # Device ID from Fermentrack
    apiKey: str  # API key from Fermentrack