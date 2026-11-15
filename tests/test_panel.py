"""Focused tests for the coordinator and light-bar service without a HA runtime."""

import asyncio
import copy
import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

import probatio
import yaml
from jinja2 import StrictUndefined
from jinja2.nativetypes import NativeEnvironment


def install_homeassistant_stubs():
    """Provide the HA interfaces used while importing the integration."""
    names = (
        "homeassistant", "homeassistant.config_entries", "homeassistant.const",
        "homeassistant.core", "homeassistant.exceptions", "homeassistant.helpers",
        "homeassistant.helpers.config_validation", "homeassistant.helpers.aiohttp_client",
        "homeassistant.helpers.update_coordinator", "homeassistant.helpers.entity_platform",
        "homeassistant.components", "homeassistant.components.number",
        "homeassistant.components.sensor", "homeassistant.components.switch",
    )
    modules = {name: types.ModuleType(name) for name in names}
    for name, module in modules.items():
        if "." in name:
            setattr(modules[name.rpartition(".")[0]], name.rpartition(".")[2], module)
    class HomeAssistantError(Exception):
        pass

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator

    class Classes:
        SWITCH = "switch"
        DURATION = "duration"
        ILLUMINANCE = "illuminance"
        MEASUREMENT = "measurement"

    modules["homeassistant.exceptions"].HomeAssistantError = HomeAssistantError
    modules["homeassistant.config_entries"].ConfigEntry = type("ConfigEntry", (), {})
    modules["homeassistant.core"].HomeAssistant = object
    modules["homeassistant.core"].ServiceCall = object
    const = modules["homeassistant.const"]
    const.CONF_HOST, const.CONF_PASSWORD, const.CONF_USERNAME = "host", "password", "username"
    const.LIGHT_LUX = "lx"
    const.UnitOfTime = types.SimpleNamespace(MINUTES="min")
    cv = modules["homeassistant.helpers.config_validation"]
    cv.string = str
    cv.boolean = bool
    cv.byte = probatio.All(probatio.Coerce(int), probatio.Byte())
    clients = modules["homeassistant.helpers.aiohttp_client"]
    clients.async_create_clientsession = clients.async_get_clientsession = lambda *a, **k: None
    update = modules["homeassistant.helpers.update_coordinator"]
    update.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
    update.CoordinatorEntity = CoordinatorEntity
    modules["homeassistant.helpers.entity_platform"].AddEntitiesCallback = object
    modules["homeassistant.components.number"].NumberDeviceClass = Classes
    modules["homeassistant.components.switch"].SwitchDeviceClass = Classes
    sensor = modules["homeassistant.components.sensor"]
    sensor.SensorDeviceClass = sensor.SensorStateClass = Classes
    sensor.SensorEntity = type("SensorEntity", (), {})
    return modules, HomeAssistantError


stubs, HomeAssistantError = install_homeassistant_stubs()
with patch.dict(sys.modules, stubs):
    integration = importlib.import_module("custom_components.crestron_tsw")
    coordinator_module = importlib.import_module("custom_components.crestron_tsw.coordinator")
    sensor_module = importlib.import_module("custom_components.crestron_tsw.sensor")
Coordinator = coordinator_module.CrestronDataUpdateCoordinator
Sensor = sensor_module.CrestronLightBarSensor
ROOT = Path(__file__).resolve().parents[1]
ACCESSORY = {"IsCrestronAccessoryConnected": True, "AccessoryType": "LIGHTBAR"}
COLORS = ("RED", "GREEN", "BLUE")
ANALOG = {33354: "RED", 33355: "GREEN", 33356: "BLUE"}
DIGITAL = {30025: "RED", 30026: "GREEN", 30027: "BLUE"}


class Response:
    def __init__(self, status=200, body="{}", location=None):
        self.status = status
        self.body = body
        self.headers = {"Location": location} if location else {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def text(self):
        return self.body


class Panel(Coordinator):
    def __init__(self):
        self.host = "panel"
        self.base_url = "https://panel"
        self.username = "user"
        self.password = "password"
        self.xsrf_token = "old"
        self._light_bar_lock = asyncio.Lock()
        self.channels = {color: {"brightness": 100, "control": 0} for color in COLORS}
        self.data = {"Device": {"UsbSchedulingPanelAccessory": ACCESSORY}, "other": 1}
        self.last_update_success = True
        self.commands = []
        self.fail = False
        self.ignore = False

    async def _async_ssh_run(self, command):
        self.commands.append(command)
        await asyncio.sleep(0)
        if self.fail:
            raise HomeAssistantError("Disconnected")
        operation, join, *value = command.split()
        join = int(join)
        if operation == "GETANALOGJOIN":
            return f"ANALOG={self.channels[ANALOG[join]]['brightness']}\r\n>"
        if operation == "GETDIGITALJOIN":
            return f"DIGITAL={self.channels[DIGITAL[join]]['control']}\r\n>"
        if not self.ignore:
            channel = self.channels[ANALOG[join] if operation == "SETANALOGJOIN" else DIGITAL[join]]
            channel["brightness" if operation == "SETANALOGJOIN" else "control"] = int(value[0])
        return "OK\r\n>"

    def async_set_updated_data(self, data):
        self.data = data


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, responses, method="POST", payload=None):
        panel = Panel()
        calls = []
        cookies = types.SimpleNamespace(clear=lambda: calls.append("clear"))

        def request(*args, **kwargs):
            calls.append((args, kwargs))
            return responses.pop(0)

        panel.session = types.SimpleNamespace(request=request, cookie_jar=cookies)
        with patch.object(coordinator_module, "async_authenticate", new=AsyncMock(return_value="new")) as auth:
            result = await panel._async_api_request(method, "/Device", payload)
        return result, calls, auth

    async def test_login_redirects_retry_original_post_once(self):
        payload = {"Device": {"DeviceOperations": {"EnterStandby": True}}}
        for status in (301, 302, 303, 307, 308, 401, 403):
            with self.subTest(status=status):
                result, calls, auth = await self.request(
                    [Response(status, location="/userlogin.html"), Response(body='{"Actions": []}')],
                    payload=payload,
                )
                requests = [item for item in calls if item != "clear"]
                self.assertEqual(result, {"Actions": []})
                self.assertEqual(len(requests), 2)
                self.assertEqual([r[0][0] for r in requests], ["POST", "POST"])
                self.assertTrue(all(r[1]["json"] == payload and r[1]["allow_redirects"] is False for r in requests))
                self.assertEqual(requests[1][1]["headers"]["X-CREST-XSRF-TOKEN"], "new")
                auth.assert_awaited_once()

    async def test_persistent_login_and_invalid_responses_fail(self):
        for responses, message in (
            ([Response(301, location="/userlogin.html"), Response(301, location="/userlogin.html")], "authentication failed"),
            ([Response(302, location="/elsewhere")], "unexpected"),
            ([Response(body="<html>")], "invalid JSON"),
            ([Response(body="")], "invalid JSON"),
            ([Response(body="[]")], "JSON object"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(HomeAssistantError, message):
                    await self.request(responses)

    async def test_post_confirmation_still_required(self):
        panel = Panel()
        panel._async_api_request = AsyncMock(return_value={"Actions": []})
        with self.assertRaisesRegex(HomeAssistantError, "did not confirm"):
            await panel.async_post_api("/Device", {})
        panel._async_api_request.return_value = {
            "Actions": [{"Results": [{"StatusId": -1, "StatusInfo": "Rejected"}]}]
        }
        with self.assertRaisesRegex(HomeAssistantError, "Rejected"):
            await panel.async_post_api("/Device", {})

    async def test_login_redirect_retries_get(self):
        result, calls, auth = await self.request(
            [Response(301, location="/userlogin.html"), Response(body='{"Device": {}}')],
            method="GET",
        )
        self.assertEqual(result, {"Device": {}})
        self.assertTrue(all(call[0][0] == "GET" for call in calls if call != "clear"))
        auth.assert_awaited_once()


class LightBarTests(unittest.IsolatedAsyncioTestCase):
    async def test_mixed_color_off_and_restore(self):
        panel = Panel()
        await panel.async_set_light_bar(True, (255, 0, 128), 128)
        self.assertEqual([panel.channels[c]["brightness"] for c in COLORS], [50, 0, 25])
        self.assertEqual([panel.channels[c]["control"] for c in COLORS], [1, 0, 1])
        self.assertEqual(panel.data["other"], 1)
        sensor = Sensor(panel, types.SimpleNamespace(entry_id="entry"))
        self.assertTrue(sensor.available)
        self.assertEqual(sensor.extra_state_attributes["rgb_color"], [255, 0, 128])
        self.assertEqual(sensor.extra_state_attributes["brightness"], 128)
        saved = copy.deepcopy(panel.channels)
        await panel.async_set_light_bar(False)
        self.assertEqual(sensor.native_value, "off")
        self.assertEqual(sensor.extra_state_attributes["rgb_color"], [255, 0, 128])
        await panel.async_set_light_bar(True)
        self.assertEqual(panel.channels, saved)
        self.assertTrue(any(c == "SETANALOGJOIN 33354 50" for c in panel.commands))
        self.assertTrue(any(c == "SETDIGITALJOIN 30027 1" for c in panel.commands))
        self.assertFalse(any("LEDBAR" in c for c in panel.commands))

    async def test_primary_zero_and_low_brightness(self):
        panel = Panel()
        await panel.async_set_light_bar(True, (0, 255, 0), 1)
        self.assertEqual([panel.channels[c]["brightness"] for c in COLORS], [0, 1, 0])
        await panel.async_set_light_bar(True, (255, 0, 0), 0)
        self.assertTrue(all(not c["control"] for c in panel.channels.values()))
        await panel.async_set_light_bar(True, (0, 0, 0), 255)
        self.assertTrue(all(not c["control"] for c in panel.channels.values()))
        await panel.async_set_light_bar(True)
        self.assertEqual([panel.channels[c]["brightness"] for c in COLORS], [100, 100, 100])

    async def test_dimming_ignores_disabled_channels_while_on(self):
        panel = Panel()
        panel.channels["RED"]["control"] = 1
        panel.channels["RED"]["brightness"] = 30
        await panel.async_set_light_bar(True, brightness=128)
        self.assertEqual([panel.channels[c]["brightness"] for c in COLORS], [50, 0, 0])
        self.assertEqual([panel.channels[c]["control"] for c in COLORS], [1, 0, 0])

    async def test_errors_invalidate_feedback(self):
        for failure in ("fail", "ignore"):
            panel = Panel()
            panel.data["light_bar"] = copy.deepcopy(panel.channels)
            setattr(panel, failure, True)
            with self.assertRaises(HomeAssistantError):
                await panel.async_set_light_bar(True, (255, 0, 0), 255)
            self.assertNotIn("light_bar", panel.data)
            self.assertEqual(panel.data["other"], 1)
            self.assertFalse(panel._light_bar_lock.locked())

    async def test_concurrent_refresh_and_commands_do_not_interleave(self):
        panel = Panel()
        panel._async_api_request = AsyncMock(return_value={"Device": {"UsbSchedulingPanelAccessory": ACCESSORY}})
        panel.async_camera_stream_is_on = AsyncMock(return_value=False)
        await asyncio.wait_for(asyncio.gather(
            panel.async_set_light_bar(True, (255, 0, 0), 255),
            panel._async_update_data(),
            panel.async_set_light_bar(True, (0, 0, 255), 128),
        ), timeout=2)
        self.assertEqual(panel.channels["BLUE"]["brightness"], 50)
        self.assertEqual(panel.data["light_bar"], panel.channels)
        writes = [i for i, c in enumerate(panel.commands) if c.startswith("SET")]
        self.assertEqual(writes[:6], list(range(writes[0], writes[0] + 6)))
        self.assertEqual(writes[6:], list(range(writes[6], writes[6] + 6)))

    async def test_unsupported_accessory_skips_reads_and_service_fails(self):
        panel = Panel()
        panel._async_api_request = AsyncMock(return_value={"Device": {}})
        panel.async_camera_stream_is_on = AsyncMock(return_value=False)
        await panel._async_update_data()
        self.assertEqual(panel.commands, [])
        with self.assertRaisesRegex(HomeAssistantError, "connected"):
            await panel.async_set_light_bar(True)

    async def test_failed_poll_clears_feedback_but_keeps_api_data(self):
        panel = Panel()
        panel.data["light_bar"] = copy.deepcopy(panel.channels)
        panel._async_api_request = AsyncMock(return_value={
            "Device": {"UsbSchedulingPanelAccessory": ACCESSORY},
            "unrelated": "kept",
        })
        panel.async_camera_stream_is_on = AsyncMock(return_value=False)
        panel.fail = True
        data = await panel._async_update_data()
        self.assertNotIn("light_bar", data)
        self.assertEqual(data["unrelated"], "kept")
        self.assertFalse(Sensor(panel, types.SimpleNamespace(entry_id="entry")).available)

    async def test_invalid_join_response(self):
        panel = Panel()
        panel.channels["RED"]["brightness"] = 101
        with self.assertRaisesRegex(HomeAssistantError, "brightness"):
            await panel.async_set_light_bar(True)
        panel._async_ssh_run = AsyncMock(return_value="GETDIGITALJOIN 30025\r\nERROR 1\r\n>")
        with self.assertRaisesRegex(HomeAssistantError, "digital join"):
            await panel.async_get_digital_join(30025)

    async def test_service_schema_and_handler(self):
        schema = integration.SET_LIGHT_BAR_SCHEMA
        valid = schema({"entry_id": "panel", "rgb_color": [255, 0, 128], "brightness": 128})
        self.assertTrue(valid["enabled"])
        for data in ({}, {"entry_id": "panel", "rgb_color": [1, 2]},
                     {"entry_id": "panel", "rgb_color": [256, 0, 0]},
                     {"entry_id": "panel", "brightness": -1}):
            with self.assertRaises(probatio.Invalid):
                schema(data)
        registered = {}
        panel = Panel()
        hass = types.SimpleNamespace(
            data={"crestron_tsw": {"panel": panel}},
            services=types.SimpleNamespace(async_register=lambda domain, name, handler, **kw: registered.update(handler=handler)),
        )
        await integration.async_setup(hass, {})
        await registered["handler"](types.SimpleNamespace(data=valid))
        self.assertEqual(panel.channels["RED"]["brightness"], 50)
        with self.assertRaisesRegex(HomeAssistantError, "not loaded"):
            await registered["handler"](types.SimpleNamespace(data={"entry_id": "missing"}))

    async def test_documented_template_actions_match_service(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        block = text.split("```yaml\n", 1)[1].split("\n```", 1)[0]
        template = yaml.safe_load(block)["template"][0]
        light = template["light"][0]
        service = yaml.safe_load((ROOT / "custom_components" / "crestron_tsw" / "services.yaml").read_text())
        self.assertEqual(set(service["set_light_bar"]["fields"]), {"entry_id", "enabled", "rgb_color", "brightness"})
        panel = Panel()
        sensor = Sensor(panel, types.SimpleNamespace(entry_id="entry"))
        env = NativeEnvironment(undefined=StrictUndefined)
        variables = dict(template["variables"])
        variables.update(
            states=lambda _: sensor.native_value if sensor.available else "unavailable",
            is_state=lambda _, value: sensor.native_value == value,
            state_attr=lambda _, name: sensor.extra_state_attributes.get(name),
        )
        for action, args in (("turn_on", {}), ("set_rgb", {"r": 0, "g": 255, "b": 0, "brightness": 128}),
                             ("set_level", {"brightness": 64}), ("turn_off", {}), ("turn_on", {}),
                             ("set_rgb", {"r": 255, "g": 0, "b": 0})):
            step = light[action][0]
            self.assertEqual(step["action"], "crestron_tsw.set_light_bar")
            data = {k: env.from_string(v).render(**variables, **args) if isinstance(v, str) else v for k, v in step["data"].items()}
            data = integration.SET_LIGHT_BAR_SCHEMA(data)
            data.pop("entry_id")
            await panel.async_set_light_bar(**data)
        self.assertEqual(panel.channels["RED"]["brightness"], 25)
        self.assertTrue(env.from_string(light["availability"]).render(**variables))


if __name__ == "__main__":
    unittest.main()
