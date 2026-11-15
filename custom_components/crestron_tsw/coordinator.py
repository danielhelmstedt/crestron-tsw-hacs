"""Coordinate API, SSH, and WebSocket communication with Crestron TSW panels."""

import asyncio
from contextlib import suppress
from datetime import timedelta
import json
import logging
import re
from urllib.parse import urlsplit

import aiohttp
import asyncssh

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import ILLUMINATION_JOIN, ILLUMINATION_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

EXCLUDED_KEYS = ["CertificateStore", "Ieee8021x"]
LIGHT_BAR_JOINS = (
    ("RED", 33354, 30025),
    ("GREEN", 33355, 30026),
    ("BLUE", 33356, 30027),
)


def filter_response_data(data, excluded_keys):
    """Filter out specified keys from an API response."""
    if isinstance(data, dict):
        return {
            key: filter_response_data(value, excluded_keys)
            for key, value in data.items()
            if key not in excluded_keys
        }
    if isinstance(data, list):
        return [filter_response_data(item, excluded_keys) for item in data]
    return data


def merge_response_data(current, update):
    """Merge a partial WebSocket update into the existing device data."""
    merged = current.copy()
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_response_data(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_nested_value(data, keys, default=None):
    """Get a nested value from a dictionary."""
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key, default)
        if data is default:
            break
    return data


async def async_authenticate(
    session: aiohttp.ClientSession, host: str, username: str, password: str
) -> str:
    """Authenticate to Crestron's HTTPS API and return its XSRF token."""
    base_url = f"https://{host}"
    session.cookie_jar.clear()

    async with session.get(f"{base_url}/userlogin.html", ssl=False) as response:
        response.raise_for_status()

    async with session.post(
        f"{base_url}/userlogin.html",
        data={"login": username, "passwd": password},
        headers={"Origin": base_url, "Referer": f"{base_url}/userlogin.html"},
        allow_redirects=False,
        ssl=False,
    ) as response:
        if response.status not in (200, 302):
            response.raise_for_status()
            raise aiohttp.ClientError("Unexpected response during authentication")
        if xsrf_token := response.headers.get("CREST-XSRF-TOKEN"):
            return xsrf_token
        raise aiohttp.ClientError("Missing CREST-XSRF-TOKEN in login response")


class CrestronDataUpdateCoordinator(DataUpdateCoordinator):
    """Manage polling and pushed updates from a Crestron panel."""

    def __init__(
        self,
        hass,
        host: str,
        name: str,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize the coordinator."""
        self.host = host
        self.base_url = f"https://{host}" if username else f"http://{host}"
        self.session = session
        self.username = username
        self.password = password
        self.xsrf_token = None
        self._ssh_connection = None
        self._ssh_process = None
        self._ssh_command_lock = asyncio.Lock()
        self._light_bar_lock = asyncio.Lock()
        self._websocket_task = None
        self._illumination_task = None
        super().__init__(
            hass, _LOGGER, name=name, update_interval=timedelta(seconds=30)
        )
        self.data = {}

    async def _async_update_data(self):
        """Fetch the panel state."""
        illumination = self.data.get("illumination")
        response_data = await self._async_api_request("GET", "/Device")
        self.data = filter_response_data(response_data, EXCLUDED_KEYS)
        if illumination is not None:
            self.data["illumination"] = illumination
        self.data["Model"] = get_nested_value(
            response_data,
            ["Device", "DeviceInfo", "Model"],
        )
        self.data["SerialNumber"] = get_nested_value(
            response_data,
            ["Device", "DeviceInfo", "SerialNumber"],
        )
        self.data["MacAddress"] = get_nested_value(
            response_data,
            ["Device", "DeviceInfo", "MacAddress"],
        )
        self.data["DeviceVersion"] = get_nested_value(
            response_data, ["Device", "DeviceInfo", "DeviceVersion"]
        )

        if self.username and self.password:
            try:
                self.data[
                    "camera_stream_is_on"
                ] = await self.async_camera_stream_is_on()
            except (asyncssh.Error, HomeAssistantError, OSError, TimeoutError):
                _LOGGER.debug("Unable to read camera stream status from %s", self.host)

        if self.username and self.password and self._light_bar_connected():
            async with self._light_bar_lock:
                try:
                    self.data["light_bar"] = await self._async_read_light_bar_channels()
                except (asyncssh.Error, HomeAssistantError, OSError, TimeoutError) as err:
                    self.data.pop("light_bar", None)
                    _LOGGER.warning(
                        "Unable to read light bar from %s: %s", self.host, err
                    )

        return self.data

    def _light_bar_connected(self) -> bool:
        """Check the API's USB accessory capability before using its joins."""
        accessory = get_nested_value(
            self.data, ["Device", "UsbSchedulingPanelAccessory"], {}
        )
        return (
            isinstance(accessory, dict)
            and accessory.get("IsCrestronAccessoryConnected") is True
            and str(accessory.get("AccessoryType", "")).upper() == "LIGHTBAR"
        )

    def async_start_illumination_poll(self, config_entry) -> None:
        """Start polling the illumination join independently of API updates."""
        if self.username and self.password and self._illumination_task is None:
            self._illumination_task = config_entry.async_create_background_task(
                self.hass,
                self._async_illumination_loop(),
                "crestron_tsw illumination polling",
            )

    async def _async_illumination_loop(self) -> None:
        """Poll the illumination analog join once per second."""
        loop = asyncio.get_running_loop()
        while True:
            poll_started = loop.time()
            try:
                value = await self.async_get_analog_join(ILLUMINATION_JOIN)
            except (asyncssh.Error, HomeAssistantError, OSError, TimeoutError):
                _LOGGER.debug("Unable to read illumination join from %s", self.host)
            else:
                if value != self.data.get("illumination"):
                    updated_data = self.data.copy()
                    updated_data["illumination"] = value
                    self.async_set_updated_data(updated_data)

            await asyncio.sleep(
                max(0, ILLUMINATION_UPDATE_INTERVAL - (loop.time() - poll_started))
            )

    async def async_post_api(
        self, path: str, payload: dict, *, update_data: bool = True
    ) -> dict:
        """Post data to the device API and return its response."""
        response = await self._async_api_request("POST", path, payload)
        results = [
            result
            for action in response.get("Actions", [])
            for result in action.get("Results", [])
        ]
        if not results:
            raise HomeAssistantError("Panel did not confirm the API update")
        for result in results:
            status_id = result.get("StatusId", -1)
            if not isinstance(status_id, int) or status_id < 0:
                raise HomeAssistantError(
                    result.get("StatusInfo", "Panel rejected the API update")
                )

        if update_data:
            self.async_set_updated_data(merge_response_data(self.data, payload))
        return response

    async def _async_api_request(
        self, method: str, path: str, payload: dict | None = None
    ) -> dict:
        """Make an API request, refreshing an expired authenticated session once."""
        for attempt in range(2):
            if self.username and self.xsrf_token is None:
                self.xsrf_token = await async_authenticate(
                    self.session, self.host, self.username, self.password
                )

            headers = {}
            if self.username:
                headers["Referer"] = f"{self.base_url}/"
                if method == "POST":
                    headers["X-CREST-XSRF-TOKEN"] = self.xsrf_token

            request_kwargs = {"headers": headers, "ssl": False}
            if payload is not None:
                request_kwargs["json"] = payload

            async with self.session.request(
                method, f"{self.base_url}{path}", allow_redirects=False, **request_kwargs
            ) as response:
                login_redirect = (
                    response.status in (301, 302, 303, 307, 308)
                    and urlsplit(response.headers.get("Location", "")).path
                    == "/userlogin.html"
                )
                if self.username and (response.status in (401, 403) or login_redirect):
                    self.xsrf_token = None
                    self.session.cookie_jar.clear()
                    if attempt:
                        raise HomeAssistantError(
                            "Crestron authentication failed after retry; "
                            "check the panel credentials"
                        )
                    continue
                response.raise_for_status()
                if 300 <= response.status < 400:
                    raise HomeAssistantError(
                        f"Crestron API {method} {path} returned an unexpected "
                        f"HTTP {response.status} redirect"
                    )
                response_text = await response.text()
                _LOGGER.debug("Received device response: %s", response_text)
                try:
                    data = json.loads(
                        response_text.removeprefix("\ufeff"), strict=False
                    )
                except json.JSONDecodeError as err:
                    raise HomeAssistantError(
                        f"Crestron API {method} {path} returned invalid JSON"
                    ) from err
                if not isinstance(data, dict):
                    raise HomeAssistantError(
                        f"Crestron API {method} {path} did not return a JSON object"
                    )
                return data

        raise aiohttp.ClientError("Crestron authentication failed after retry")

    def async_start_websocket(self, config_entry) -> None:
        """Start receiving device updates over WebSocket when authenticated."""
        if self.username and self.password and self._websocket_task is None:
            self._websocket_task = config_entry.async_create_background_task(
                self.hass,
                self._async_websocket_loop(),
                "crestron_tsw websocket listener",
            )

    async def _async_websocket_loop(self) -> None:
        """Enable the panel WebSocket and process pushed device updates."""
        retry_interval = 5
        while True:
            try:
                error = await self._async_listen_websocket()
            except asyncio.CancelledError:
                raise
            except (
                aiohttp.ClientError,
                asyncssh.Error,
                HomeAssistantError,
                OSError,
            ) as err:
                error = str(err)

            _LOGGER.warning(
                "Crestron WebSocket disconnected from %s: %s; retrying in %s seconds",
                self.host,
                error,
                retry_interval,
            )
            await asyncio.sleep(retry_interval)
            retry_interval = min(retry_interval * 2, 300)

    async def _async_listen_websocket(self) -> str:
        """Connect and listen until the panel closes the WebSocket."""
        await self._async_api_request("GET", "/Device")
        await self._async_ssh_run("WEBSOCKET ON")
        async with self.session.ws_connect(
            f"{self.base_url}/websockify",
            headers={
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/userlogin.html",
                "X-CREST-XSRF-TOKEN": self.xsrf_token,
            },
            heartbeat=30,
            ssl=False,
        ) as websocket:
            await websocket.send_str("/Device")
            _LOGGER.info("Connected to Crestron WebSocket on %s", self.host)
            async for message in websocket:
                if message.type is aiohttp.WSMsgType.TEXT:
                    self._async_process_websocket_message(message.data)
                elif message.type is aiohttp.WSMsgType.ERROR:
                    return f"WebSocket error: {websocket.exception()}"
        return "WebSocket connection closed"

    def _async_process_websocket_message(self, message: str) -> None:
        """Merge a pushed device update into coordinator data."""
        try:
            update = json.loads(message.removeprefix("\ufeff"))
        except json.JSONDecodeError:
            _LOGGER.debug("Ignoring non-JSON Crestron WebSocket message")
            return
        if not isinstance(update, dict):
            return

        filtered_update = filter_response_data(update, EXCLUDED_KEYS)
        updated_data = merge_response_data(self.data, filtered_update)
        updated_data["Model"] = get_nested_value(
            updated_data, ["Device", "DeviceInfo", "Model"], self.data.get("Model")
        )
        updated_data["SerialNumber"] = get_nested_value(
            updated_data,
            ["Device", "DeviceInfo", "SerialNumber"],
            self.data.get("SerialNumber"),
        )
        updated_data["MacAddress"] = get_nested_value(
            updated_data,
            ["Device", "DeviceInfo", "MacAddress"],
            self.data.get("MacAddress"),
        )
        updated_data["DeviceVersion"] = get_nested_value(
            updated_data,
            ["Device", "DeviceInfo", "DeviceVersion"],
            self.data.get("DeviceVersion"),
        )
        if updated_data != self.data:
            self.data = updated_data
            self.async_set_updated_data(updated_data)

    async def async_get_analog_join(self, join_number: int) -> float:
        """Read a Crestron analog join from the panel console."""
        response = await self._async_ssh_run(f"GETANALOGJOIN {join_number}")
        match = re.search(
            r"\bANALOG\s*=\s*([+-]?\d+(?:\.\d+)?)\b",
            response,
            re.IGNORECASE,
        )
        if match is None:
            raise HomeAssistantError(
                f"Unexpected analog join response for {join_number}: {response.strip()}"
            )
        return float(match.group(1))

    async def async_get_digital_join(self, join_number: int) -> bool:
        """Read a Crestron digital join from the panel console."""
        response = await self._async_ssh_run(f"GETDIGITALJOIN {join_number}")
        values = re.findall(
            r"\bDIGITAL\s*=\s*(0|1)\b",
            response,
            re.IGNORECASE,
        )
        if not values:
            raise HomeAssistantError(
                f"Unexpected digital join response for {join_number}: {response.strip()}"
            )
        return values[-1] == "1"

    async def _async_read_light_bar_channels(self) -> dict:
        """Read the USB light-bar analog and digital joins."""
        channels = {}
        for color, analog_join, digital_join in LIGHT_BAR_JOINS:
            brightness = await self.async_get_analog_join(analog_join)
            if not 0 <= brightness <= 100 or not brightness.is_integer():
                raise HomeAssistantError(
                    f"Unexpected USB light-bar brightness for {color}: {brightness}"
                )
            channels[color] = {
                "brightness": int(brightness),
                "control": int(await self.async_get_digital_join(digital_join)),
            }
        return channels

    async def async_set_light_bar(
        self,
        enabled: bool,
        rgb_color: tuple[int, int, int] | list[int] | None = None,
        brightness: int | None = None,
    ) -> None:
        """Set USB accessory joins and verify their readback."""
        async with self._light_bar_lock:
            try:
                if (
                    not self.username
                    or not self.password
                    or not self._light_bar_connected()
                ):
                    raise HomeAssistantError(
                        "A connected USB light bar and SSH credentials are required"
                    )
                current = await self._async_read_light_bar_channels()
                levels = [
                    current[color]["brightness"] for color, _, _ in LIGHT_BAR_JOINS
                ]
                if enabled:
                    is_on = any(
                        current[color]["control"] and current[color]["brightness"]
                        for color, _, _ in LIGHT_BAR_JOINS
                    )
                    active_levels = [
                        current[color]["brightness"]
                        if not is_on or current[color]["control"]
                        else 0
                        for color, _, _ in LIGHT_BAR_JOINS
                    ]
                    rgb = rgb_color if rgb_color is not None else active_levels
                    if rgb_color is None and not max(rgb):
                        rgb = (255, 255, 255)
                    peak = max(rgb)
                    level = (
                        brightness / 255 * 100
                        if brightness is not None
                        else max(active_levels) or 100
                    )
                    levels = [
                        max(1, round(value / peak * level))
                        if value and peak and level
                        else 0
                        for value in rgb
                    ]
                expected = {}
                for (color, analog_join, digital_join), level in zip(
                    LIGHT_BAR_JOINS, levels, strict=True
                ):
                    control = int(enabled and level > 0)
                    if enabled:
                        await self._async_ssh_run(f"SETANALOGJOIN {analog_join} {level}")
                    await self._async_ssh_run(f"SETDIGITALJOIN {digital_join} {control}")
                    expected[color] = {"brightness": level, "control": control}
                actual = await self._async_read_light_bar_channels()
                if actual != expected:
                    raise HomeAssistantError(
                        "Panel light-bar feedback did not match the requested settings"
                    )
                updated_data = self.data.copy()
                updated_data["light_bar"] = actual
                self.async_set_updated_data(updated_data)
            except (asyncssh.Error, HomeAssistantError, OSError, TimeoutError):
                updated_data = self.data.copy()
                updated_data.pop("light_bar", None)
                self.async_set_updated_data(updated_data)
                raise

    async def async_camera_stream_is_on(self) -> bool:
        """Return whether the panel's RTSP camera stream is enabled."""
        response = await self._async_ssh_run("CAMERASTREAMENABLE")
        return self._parse_camera_stream_status(response)

    async def async_set_camera_stream(self, enabled: bool) -> dict[str, str | bool]:
        """Set camera streaming and return command and state feedback."""
        state = "ON" if enabled else "OFF"
        command_response = await self._async_ssh_run(f"CAMERASTREAMENABLE {state}")
        status = await self._async_ssh_run("CAMERASTREAMENABLE")
        confirmation = self._parse_camera_stream_confirmation(command_response, enabled)
        actual_state = self._parse_camera_stream_status(status)
        if actual_state != enabled:
            raise HomeAssistantError(
                f"Panel reported camera streaming {'on' if actual_state else 'off'} "
                f"after setting it {state.lower()}"
            )
        return {
            "confirmation": confirmation,
            "current_status": status.strip(),
            "is_on": actual_state,
        }

    @staticmethod
    def _parse_camera_stream_confirmation(response: str, enabled: bool) -> str:
        """Validate the panel's camera-stream command confirmation."""
        clean_response = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", response)
        state = "on" if enabled else "off"
        matches = re.findall(
            rf"set camera streaming\s+{state}\b", clean_response, re.IGNORECASE
        )
        if not matches:
            raise HomeAssistantError(
                f"Unexpected camera stream command response: {response.strip()}"
            )
        return matches[-1]

    @staticmethod
    def _parse_camera_stream_status(response: str) -> bool:
        """Parse the state from the panel's CAMERASTREAMENABLE response."""
        clean_response = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", response)
        matches = re.findall(
            r"current camera streaming\s*:\s*(on|off)\b",
            clean_response,
            re.IGNORECASE,
        )
        if not matches:
            raise HomeAssistantError(
                f"Unexpected camera stream status response: {response.strip()}"
            )
        return matches[-1].casefold() == "on"

    async def _async_ssh_connection(self):
        """Connect to the panel's SSH console using the configured credentials."""
        if not self.username or not self.password:
            raise HomeAssistantError("SSH credentials are required for this panel")
        if self._ssh_connection is None or self._ssh_connection.is_closed():
            self._ssh_connection = await asyncssh.connect(
                self.host,
                username=self.username,
                password=self.password,
                known_hosts=None,
            )
            self._ssh_process = None
        return self._ssh_connection

    async def _async_ssh_run(self, command: str) -> str:
        """Run a command in the persistent panel console channel."""
        async with self._ssh_command_lock:
            try:
                connection = await self._async_ssh_connection()
                if self._ssh_process is None:
                    self._ssh_process = await connection.create_process(
                        term_type="xterm"
                    )
                    await self._async_ssh_read_prompt()
                self._ssh_process.stdin.write(f"{command}\r")
                await self._ssh_process.stdin.drain()
                return await self._async_ssh_read_prompt()
            except (asyncssh.Error, HomeAssistantError, OSError, TimeoutError) as err:
                await self._async_close_ssh()
                if isinstance(err, HomeAssistantError):
                    raise
                raise HomeAssistantError(
                    f"Failed to run command on Crestron panel {self.host}"
                ) from err

    async def _async_ssh_read_prompt(self) -> str:
        """Read console output through the next command prompt."""
        output = []
        async with asyncio.timeout(10):
            while len(output) < 4096:
                character = await self._ssh_process.stdout.read(1)
                if not character:
                    raise HomeAssistantError("SSH console channel closed")
                output.append(character)
                response = "".join(output)
                visible_response = re.sub(
                    r"\x1b\[[0-?]*[ -/]*[@-~]", "", response
                ).rstrip()
                if visible_response.endswith(">"):
                    return response
        raise HomeAssistantError("Timed out waiting for the SSH console prompt")

    async def _async_close_ssh(self) -> None:
        """Close the persistent SSH shell and connection."""
        if self._ssh_process is not None:
            self._ssh_process.close()
            with suppress(asyncssh.Error):
                await self._ssh_process.wait_closed()
            self._ssh_process = None
        if self._ssh_connection is not None:
            self._ssh_connection.close()
            with suppress(asyncssh.Error):
                await self._ssh_connection.wait_closed()
            self._ssh_connection = None

    async def async_close(self) -> None:
        """Stop background tasks and close the SSH connection."""
        for task_name in ("_websocket_task", "_illumination_task"):
            if (task := getattr(self, task_name)) is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                setattr(self, task_name, None)
        await self._async_close_ssh()
