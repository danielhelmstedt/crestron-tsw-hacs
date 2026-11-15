# Crestron TSW Integration

This is a custom component for integrating Crestron TSW-Series touch screens with Home Assistant. Supports HTTP/S, WebSockets and SSH.


##  Entities
- **Switches:** 
    - Camera Enabled
    - Camera RTSP Stream
    - Auto Brightness
    - Audio Muted
    - Media Muted
    - Beep Enabled
    - Screen Saver Enabled
    - Wake on Proximity (on supported TSW-x70 models)
- **Buttons:** 
    - Enter Standby
    - Exit Standby
- **Numbers:** 
    - Brightness
    - Volume (Controls volume of media played through EMS URL)
    - Media Volume (Unsure what this controls)
    - Beep Volume
    - Standby Timeout (0-120 minutes)
    - Screen Saver Brightness
- **Sensors:** 
    - Display Status (On, Standby)
    - Illumination Level (Ambient light sensor, in Lux).
    - Light Bar Status (USB accessory feedback, when authenticated).
- **Application Selection:** 
    - Drop-down list populated from the panel's supported application modes.
- **Application URL:** 
    - Text entry for the 'EMS/Crestron General Web' Application URL

## Authenticated Features

**SSH, HTTPS & WebSockets:**    
When authentication is configured, the integration opens a persistent SSH connection, then calls `WEBSOCKET ON` and upgrades the API connection to a WebSocket connection, allowing realtime entity updates.
If a panel does not have authentication enabled, it will fall back to REST via HTTP.

**Illumination Sensor:**    
With authentication enabled, the integration polls `GETANALOGJOIN 17219` over SSH every 1s, returning a Lux value between 0-99.

**RTSP Streaming:**     
With authentication enabled, the ***Camera RTSP Stream*** switch controls the panel over SSH using `CAMERASTREAMENABLE ON|OFF`. The integration checks the command confirmation and reported state after each change, and updates periodically.

The RTSP stream is available at <rtsp://IP_ADDRESS:8554/camera.sdp>.    
**Note: The stream does not include audio.**

### USB RGB light bar

A connected Crestron USB light bar and configured panel credentials (including SSH
access) are required. The panel must report the accessory as connected with type
`LIGHTBAR`. The integration reads the USB accessory joins on each normal refresh
and verifies writes against those joins. Other panels do not poll these joins.

The `crestron_tsw.set_light_bar` action accepts `entry_id` (required), `enabled`
(default `true`), and optional `rgb_color` (three values from 0 to 255) and
`brightness` (0 to 255). Omitted color and brightness retain the current settings.
Turning off preserves channel levels; a zero brightness or black color turns the
bar off. The panel uses integer percentages, so low brightness and colors are
quantized. When all stored levels are zero, turning on without a color defaults
to white at full brightness.

To add a full RGB light, add this example to your Home Assistant YAML, replacing
`YOUR_CONFIG_ENTRY_ID` with the panel's configuration entry ID and
`sensor.crestron_light_bar_status` with the actual **Light Bar Status** entity ID
from the panel's device page. Use a distinct `unique_id` for each template light.
Restart Home Assistant or reload template entities after updating the YAML.

```yaml
template:
  - variables:
      panel_entry_id: YOUR_CONFIG_ENTRY_ID
      feedback_sensor: sensor.crestron_light_bar_status
    light:
      - name: Crestron light bar
        unique_id: crestron_light_bar_template
        availability: "{{ states(feedback_sensor) not in ['unknown', 'unavailable'] }}"
        state: "{{ is_state(feedback_sensor, 'on') }}"
        level: "{{ state_attr(feedback_sensor, 'brightness') | int(0) }}"
        rgb: "{{ state_attr(feedback_sensor, 'rgb_color') or [255, 255, 255] }}"
        turn_on:
          - action: crestron_tsw.set_light_bar
            data:
              entry_id: "{{ panel_entry_id }}"
        turn_off:
          - action: crestron_tsw.set_light_bar
            data:
              entry_id: "{{ panel_entry_id }}"
              enabled: false
        set_level:
          - action: crestron_tsw.set_light_bar
            data:
              entry_id: "{{ panel_entry_id }}"
              brightness: "{{ brightness }}"
        set_rgb:
          - action: crestron_tsw.set_light_bar
            data:
              entry_id: "{{ panel_entry_id }}"
              rgb_color: "{{ [r, g, b] }}"
              brightness: "{{ brightness | default(state_attr(feedback_sensor, 'brightness') or 255) }}"
```

## Installation (HACS) - Recommended

1. Have [HACS](https://hacs.xyz/) installed.
2. Add `https://github.com/danielhelmstedt/crestron-tsw-hacs` as a
   [custom repository](https://hacs.xyz/docs/faq/custom_repositories/) with
   **Type: Integration**.
3. In HACS, find **Crestron TSW** and click **Download**, then restart Home
   Assistant for the installation to take effect.
4. Go to **Settings → Devices & services → Add integration**, search for
   **Crestron TSW**, and complete setup.

## Installation (Manual)

1. Download this repository as a ZIP and unzip the archive.
2. Copy `custom_components/crestron_tsw` into
   `/config/custom_components/crestron_tsw`.
   - Create the `custom_components` folder if it does not exist.
3. Restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration**, search for
   **Crestron TSW**, and complete setup.

## Support

If you encounter any issues, please open an issue on the [GitHub repository](https://github.com/danielhelmstedt/crestron-tsw-hacs).

## Tests

The focused regression suite uses Python's `unittest` with stubbed Home Assistant
interfaces. Install `aiohttp`, `asyncssh`, `probatio`, `PyYAML`, and `Jinja2`,
then run `python -m unittest discover -s tests -v`. It does not replace testing
in Home Assistant or on a physical panel.

## License

This project is licensed under the [MIT License](LICENSE).
