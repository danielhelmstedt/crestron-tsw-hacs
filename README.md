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

If you encounter any issues, please open an issue on the [GitHub repository](https://github.com/danielhelmstedt/crestron-tsw-hacs.

## License

This project is licensed under the [MIT License](LICENSE).
