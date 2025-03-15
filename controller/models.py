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


class ControlSettings(BaseModel):
    """Controller settings."""
    
    mode: ControllerMode
    beer_set: float = Field(0.0, alias="beerSet")
    fridge_set: float = Field(0.0, alias="fridgeSet")
    heat_estimator: float = Field(0.0, alias="heatEst")
    cool_estimator: float = Field(0.0, alias="coolEst")


class ControlConstants(BaseModel):
    """Controller constants."""
    
    # Temperature settings
    temp_format: str = Field("C", alias="tempFormat")
    temp_setting_min: float = Field(1.0, alias="tempSettingMin")
    temp_setting_max: float = Field(30.0, alias="tempSettingMax")
    
    # Control algorithms
    pid_max: float = Field(10.0, alias="pidMax")
    k_p: float = Field(20.0, alias="Kp")
    k_i: float = Field(0.5, alias="Ki")
    k_d: float = Field(2.0, alias="Kd")
    imax: float = Field(10.0, alias="iMaxError")
    i_max_slope: float = Field(0.1, alias="iMaxSlope")
    
    # Filter time constants
    beer_fast_filter: int = Field(400, alias="beerFastFilt")
    beer_slow_filter: int = Field(1200, alias="beerSlowFilt")
    beer_slope_filter: int = Field(1800, alias="beerSlopeFilt")
    fridge_fast_filter: int = Field(400, alias="fridgeFastFilt")
    fridge_slow_filter: int = Field(1200, alias="fridgeSlowFilt")
    fridge_slope_filter: int = Field(1200, alias="fridgeSlopeFilt")


class MinimumTime(BaseModel):
    """Minimum time settings."""
    
    min_cool_time: int = Field(300, alias="minCoolTime")
    min_cool_idle_time: int = Field(300, alias="minCoolIdleTime")
    min_heat_time: int = Field(300, alias="minHeatTime")
    min_heat_idle_time: int = Field(300, alias="minHeatIdleTime")
    min_idle_time: int = Field(300, alias="minIdleTime")


class FullConfig(BaseModel):
    """Full controller configuration."""
    
    control_settings: ControlSettings = Field(..., alias="control_settings")
    control_constants: ControlConstants = Field(..., alias="control_constants")
    minimum_times: MinimumTime = Field(..., alias="minimum_times")
    devices: List[Device] = Field(..., alias="devices")


class TemperatureData(BaseModel):
    """Temperature data from controller."""
    
    beer_temp: Optional[float] = Field(None, alias="beerTemp")
    beer_set: float = Field(0.0, alias="beerSet")
    fridge_temp: Optional[float] = Field(None, alias="fridgeTemp")
    fridge_set: float = Field(0.0, alias="fridgeSet")
    room_temp: Optional[float] = Field(None, alias="roomTemp")


class ControllerStatus(BaseModel):
    """Controller status for API."""
    
    mode: str
    beer_set: float
    fridge_set: float
    heat_est: float
    cool_est: float
    temperature_data: Dict[str, Optional[float]]
    lcd_content: Dict[str, str]
    changes_pending: bool = False
    firmware_version: Optional[str] = None


class MessageStatus(BaseModel):
    """Message flags for communication with Fermentrack."""
    
    # Device control messages
    reset_eeprom: bool = False
    reset_connection: bool = False
    restart_device: bool = False
    refresh_lcd: bool = False
    
    # Device update messages
    updated_cc: bool = False
    updated_cs: bool = False
    updated_mt: bool = False
    updated_devices: Any = False
    refresh_config: bool = False
    
    # Default setting messages
    default_cc: bool = False
    default_cs: bool = False
    default_devices: bool = False
    
    # Mode and setpoint updates
    update_mode: Optional[str] = None
    update_beer_set: Optional[float] = None
    update_fridge_set: Optional[float] = None
    
    # Config updates
    update_control_settings: Optional[Dict[str, Any]] = None
    update_control_constants: Optional[Dict[str, Any]] = None
    update_devices: Optional[List[Dict[str, Any]]] = None


class SerializedDevice(BaseModel):
    """Device for API serialization."""
    
    id: int
    chamber: int
    beer: int
    type: str
    hardware_type: str
    pin: int
    pin_type: str
    calibration_offset: float = 0.0
    calibration_factor: float = 1.0
    function: str = "0"
    value: Optional[float] = None
    
    class Config:
        """Pydantic configuration."""
        
        populate_by_name = True

    @classmethod
    def from_device(cls, device: Device) -> 'SerializedDevice':
        """Convert Device to SerializedDevice."""
        return cls(
            id=device.id,
            chamber=device.chamber,
            beer=device.beer,
            type=device.type,
            hardware_type=device.hardware_type,
            pin=device.pin,
            pin_type=device.pin_type,
            calibration_offset=device.calibration_offset,
            calibration_factor=device.calibration_factor,
            function=device.function,
            value=device.value
        )