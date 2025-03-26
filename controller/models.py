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


class SensorType(str, Enum):
    """Sensor types."""
    
    TEMP_SENSOR = "0"
    SWITCH_SENSOR = "1"
    TEMP_SETTING_ACTUATOR = "2"
    PWM_ACTUATOR = "3"
    DIGITAL_ACTUATOR = "4"


class DeviceFunction(str, Enum):
    """Device functions."""
    
    NONE = "0"
    CHAMBER_DOOR = "1"
    CHAMBER_HEAT = "2"
    CHAMBER_COOL = "3"
    CHAMBER_LIGHT = "4"
    CHAMBER_FAN = "5"
    CHAMBER_TEMP = "6"
    ROOM_TEMP = "7"
    BEER_TEMP = "8"
    BEER_HEAT = "9"
    BEER_COOL = "10"
    BEER_SG = "11"


class PinType(str, Enum):
    """Pin types."""
    
    NOT_ASSIGNED = "0"
    DIGITAL_INPUT = "1"
    DIGITAL_OUTPUT = "2"
    ANALOG_INPUT = "3"
    ANALOG_OUTPUT = "4"
    DIGITAL_INPUT_PULLUP = "5"
    DIGITAL_OUTPUT_FAST = "6"


class Device(BaseModel):
    """BrewPi device (sensor/actuator)."""
    
    id: int
    chamber: int
    beer: int
    type: SensorType
    hardware_type: str
    pin: int
    pin_type: PinType
    calibration_offset: float = 0.0
    calibration_factor: float = 1.0
    function: DeviceFunction = DeviceFunction.NONE
    value: Optional[float] = None
    
    @validator('value')
    def validate_value(cls, value, values):
        """Validate sensor value based on type."""
        if value is None:
            return value
            
        device_type = values.get('type')
        
        if device_type == SensorType.SWITCH_SENSOR:
            # For switch sensors, value should be 0 or 1
            return 1 if value > 0 else 0
            
        return value


class DeviceListItem(BaseModel):
    """Item in the device list response from controller."""
    
    c: int  # chamber
    b: int  # beer
    f: int  # function
    h: int  # hardware type
    p: int  # pin
    x: bool  # value
    d: bool  # deactivated
    r: str  # name/role
    i: int  # id


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
    
    These fields match the device list response from the controller:
    c: chamber
    b: beer
    f: function (device function as integer)
    h: hardware type (as integer)
    p: pin
    x: value (boolean or sensor value)
    d: deactivated
    r: name/role (string)
    i: id
    a: address (optional, for OneWire devices)
    j: calibration offset (optional, for sensors)
    v: value as string (optional, for sensors)
    """
    
    c: int  # chamber
    b: int  # beer
    f: int  # function
    h: int  # hardware type
    p: int  # pin
    x: bool  # value as boolean
    d: bool = False  # deactivated
    r: str = ""  # name/role
    i: int  # id
    a: Optional[str] = None  # address (OneWire devices)
    j: Optional[str] = None  # calibration offset
    v: Optional[str] = None  # value as string
    
    class Config:
        """Pydantic configuration."""
        
        populate_by_name = True

    # TODO - Check if this is needed?
    @classmethod
    def from_device(cls, device: Device) -> 'SerializedDevice':
        """Convert Device to SerializedDevice in the compact format."""
        # Convert hardware_type string to integer code
        hw_type = 1  # Default to temp sensor
        
        # Convert function to integer
        function_value = int(device.function.value) if hasattr(device.function, 'value') else 0
        
        # Format value as string for sensor devices, or use boolean value for actuators
        is_sensor = device.type in [SensorType.TEMP_SENSOR]
        device_value = device.value
        value_str = f"{device_value:.3f}" if device_value is not None and is_sensor else None
        
        # Value as boolean (x) depends on device type
        bool_value = False
        if device_value is not None:
            if is_sensor:
                bool_value = device_value > 0
            else:
                bool_value = device_value > 0
        
        return cls(
            c=device.chamber,
            b=device.beer,
            f=function_value,
            h=hw_type,
            p=device.pin,
            x=bool_value,
            d=False,  # Default to not deactivated
            r=f"Device {device.id}",  # Default name
            i=device.id,
            j=f"{device.calibration_offset:.3f}" if is_sensor else None,
            v=value_str
        )


class FullConfig(BaseModel):
    """Full controller configuration in Fermentrack format."""
    
    cs: ControlSettings  # Control settings
    cc: ControlConstants  # Control constants
    devices: List[SerializedDevice]  # Device list
    deviceID: str  # Device ID from Fermentrack
    apiKey: str  # API key from Fermentrack