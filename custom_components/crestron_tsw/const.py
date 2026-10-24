"""Define constant variables."""

from homeassistant.components.number import NumberDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.switch import SwitchDeviceClass
from homeassistant.const import LIGHT_LUX, UnitOfTime

DOMAIN = "crestron_tsw"
CONF_USE_WEBSOCKET = "use_websocket"
ILLUMINATION_JOIN = 17219
ILLUMINATION_UPDATE_INTERVAL = 1
PLATFORMS = ["sensor", "button", "switch", "number", "select", "text"]

ENTITIES_TO_EXPOSE = [
    {
        "type": "switch",
        "name": "Camera Enabled",
        "icon": "mdi:camera",
        "device_class": SwitchDeviceClass.SWITCH,
        "value_path": ["Device", "Camera", "IsEnabled"],
    },
    {
        "type": "switch",
        "name": "Auto Brightness",
        "icon": "mdi:brightness-auto",
        "device_class": SwitchDeviceClass.SWITCH,
        "value_path": ["Device", "Display", "Lcd", "AutoBrightness", "IsEnabled"],
    },
    {
        "type": "switch",
        "name": "Audio Muted",
        "icon": "mdi:volume-mute",
        "device_class": SwitchDeviceClass.SWITCH,
        "value_path": ["Device", "Display", "Audio", "IsMuted"],
    },
    {
        "type": "switch",
        "name": "Media Muted",
        "icon": "mdi:volume-mute",
        "device_class": SwitchDeviceClass.SWITCH,
        "value_path": ["Device", "Display", "Audio", "IsMediaMuted"],
    },
    {
        "type": "switch",
        "name": "Beep Enabled",
        "icon": "mdi:volume",
        "device_class": SwitchDeviceClass.SWITCH,
        "value_path": ["Device", "Display", "Audio", "IsBeepEnabled"],
    },
    {
        "type": "switch",
        "name": "Screen Saver Enabled",
        "icon": "mdi:monitor",
        "device_class": SwitchDeviceClass.SWITCH,
        "value_path": ["Device", "Display", "ScreenSaver", "IsEnabled"],
    },
    {
        "type": "switch",
        "name": "Wake on Proximity",
        "icon": "mdi:motion-sensor",
        "device_class": SwitchDeviceClass.SWITCH,
        "value_path": ["Device", "ProximitySensor", "IsWakeOnProximityEnabled"],
        "requires_tsw_x70": True,
    },
    {
        "type": "ssh_switch",
        "name": "Camera RTSP Stream",
        "icon": "mdi:video-wireless",
        "device_class": SwitchDeviceClass.SWITCH,
    },
    {
        "type": "button",
        "name": "Enter Standby",
        "icon": "mdi:sleep",
        "value_path": ["Device", "DeviceOperations", "EnterStandby"],
    },
    {
        "type": "button",
        "name": "Exit Standby",
        "icon": "mdi:power",
        "value_path": ["Device", "DeviceOperations", "ExitStandby"],
    },
    {
        "type": "number",
        "name": "Brightness",
        "icon": "mdi:brightness-6",
        "value_path": ["Device", "Display", "Lcd", "Brightness"],
        "native_min_value": 0,
        "native_max_value": 100,
    },
    {
        "type": "number",
        "name": "Volume",
        "icon": "mdi:volume",
        "value_path": ["Device", "Display", "Audio", "Volume"],
        "native_min_value": 0,
        "native_max_value": 100,
    },
    {
        "type": "number",
        "name": "Media Volume",
        "icon": "mdi:volume",
        "value_path": ["Device", "Display", "Audio", "MediaVolume"],
        "native_min_value": 0,
        "native_max_value": 100,
    },
    {
        "type": "number",
        "name": "Beep Volume",
        "icon": "mdi:volume",
        "value_path": ["Device", "Display", "Audio", "BeepVolume"],
        "native_min_value": 0,
        "native_max_value": 100,
    },
    {
        "type": "number",
        "name": "Standby Timeout",
        "icon": "mdi:timer-outline",
        "device_class": NumberDeviceClass.DURATION,
        "native_unit_of_measurement": UnitOfTime.MINUTES,
        "value_path": ["Device", "Display", "Lcd", "StandbyTimeoutMinutes"],
        "native_min_value": 0,
        "native_max_value": 120,
    },
    {
        "type": "number",
        "name": "Screen Saver Brightness",
        "icon": "mdi:brightness-5",
        "value_path": ["Device", "Display", "ScreenSaver", "Brightness"],
        "native_min_value": 0,
        "native_max_value": 100,
    },
    {
        "type": "sensor",
        "name": "Display Status",
        "icon": "mdi:monitor",
        "value_path": ["Device", "Display", "CurrentState"],
    },
    {
        "type": "sensor",
        "name": "Illumination Level",
        "icon": "mdi:white-balance-sunny",
        "value_path": ["illumination"],
        "device_class": SensorDeviceClass.ILLUMINANCE,
        "native_unit_of_measurement": LIGHT_LUX,
        "state_class": SensorStateClass.MEASUREMENT,
        "requires_ssh": True,
    },
    {
        "type": "select",
        "name": "Application",
        "icon": "mdi:apps",
        "value_path": ["Device", "ThirdPartyApplications", "Mode"],
        "options_path": [
            "Device",
            "ThirdPartyApplications",
            "ApplicationsModeSupported",
        ],
    },
    {
        "type": "text",
        "name": "Application URL",
        "icon": "mdi:link",
    },
]
