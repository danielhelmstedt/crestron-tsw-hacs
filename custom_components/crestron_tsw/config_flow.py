"""Setup device via Home Assistant UI Config Flow."""

import json
import logging

import aiohttp
import probatio

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME

from .const import CONF_USE_WEBSOCKET, DOMAIN
from .coordinator import async_authenticate

_LOGGER = logging.getLogger(__name__)


def get_nested_value(data, keys, default=None):
    """Retrieve a nested value from a dictionary."""
    for key in keys:
        data = data.get(key, default)
        if data is default:
            break
    return data


async def async_validate_device(host, username, password):
    """Validate the panel and return its identifying information."""
    session_kwargs = {}
    api_url = f"http://{host}/Device"
    headers = None
    if username:
        session_kwargs = {
            "cookie_jar": aiohttp.CookieJar(unsafe=True),
            "connector": aiohttp.TCPConnector(ssl=False),
        }
        api_url = f"https://{host}/Device"
        headers = {"Referer": f"https://{host}/"}

    async with aiohttp.ClientSession(**session_kwargs) as session:
        if username:
            await async_authenticate(session, host, username, password)
        async with session.get(api_url, headers=headers, ssl=False) as response:
            response.raise_for_status()
            response_text = await response.text()
            _LOGGER.debug("Received device response: %s", response_text)
            device_info = json.loads(response_text.removeprefix("\ufeff"), strict=False)

    return {
        "model": get_nested_value(device_info, ["Device", "DeviceInfo", "Model"], ""),
        "serial_number": get_nested_value(
            device_info, ["Device", "DeviceInfo", "SerialNumber"], ""
        ),
        "mac_address": get_nested_value(
            device_info, ["Device", "DeviceInfo", "MacAddress"], ""
        ),
    }


class CrestronTSWConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crestron TSW-Series Panel."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            username = user_input.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD)
            use_websocket = user_input[CONF_USE_WEBSOCKET]

            if bool(username) != bool(password):
                errors["base"] = "invalid_auth"
            else:
                try:
                    device_info = await async_validate_device(host, username, password)
                except aiohttp.ClientResponseError as err:
                    _LOGGER.error("Error connecting to device: %s", err)
                    errors["base"] = (
                        "invalid_auth" if err.status == 403 else "cannot_connect"
                    )
                except (aiohttp.ClientError, json.JSONDecodeError) as err:
                    _LOGGER.error("Error connecting to device: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=device_info["model"] or "Crestron TSW",
                        data={
                            CONF_HOST: host,
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            CONF_USE_WEBSOCKET: use_websocket,
                            **device_info,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_HOST): str,
                    probatio.Optional(CONF_USERNAME): str,
                    probatio.Optional(CONF_PASSWORD): str,
                    probatio.Required(CONF_USE_WEBSOCKET, default=True): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        """Reconfigure the panel connection."""
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            username = user_input.get(CONF_USERNAME) or entry.data.get(CONF_USERNAME)
            password = user_input.get(CONF_PASSWORD) or entry.data.get(CONF_PASSWORD)
            use_websocket = user_input.get(
                CONF_USE_WEBSOCKET, entry.data.get(CONF_USE_WEBSOCKET, True)
            )

            if bool(username) != bool(password):
                errors["base"] = "invalid_auth"
            else:
                try:
                    device_info = await async_validate_device(host, username, password)
                except aiohttp.ClientResponseError as err:
                    _LOGGER.error("Error connecting to device: %s", err)
                    errors["base"] = (
                        "invalid_auth" if err.status == 403 else "cannot_connect"
                    )
                except (aiohttp.ClientError, json.JSONDecodeError) as err:
                    _LOGGER.error("Error connecting to device: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            **entry.data,
                            CONF_HOST: host,
                            CONF_USERNAME: username,
                            CONF_PASSWORD: password,
                            CONF_USE_WEBSOCKET: use_websocket,
                            **device_info,
                        },
                    )

        suggested_values = {
            CONF_HOST: entry.data[CONF_HOST],
            CONF_USERNAME: entry.data.get(CONF_USERNAME, ""),
            CONF_USE_WEBSOCKET: entry.data.get(CONF_USE_WEBSOCKET, True),
        }
        if user_input is not None:
            suggested_values.update(
                {
                    key: user_input[key]
                    for key in (CONF_HOST, CONF_USERNAME, CONF_USE_WEBSOCKET)
                    if key in user_input
                }
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(
                    {
                        probatio.Required(CONF_HOST): str,
                        probatio.Optional(CONF_USERNAME): str,
                        probatio.Optional(CONF_PASSWORD): str,
                        probatio.Required(
                            CONF_USE_WEBSOCKET,
                            default=entry.data.get(CONF_USE_WEBSOCKET, True),
                        ): bool,
                    }
                ),
                suggested_values=suggested_values,
            ),
            errors=errors,
        )
