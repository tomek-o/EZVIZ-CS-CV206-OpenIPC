# Open firmware for the Ezviz CS-CV206 camera

A local-only replacement firmware for the **Ezviz CS-CV206** (sold as **ezCubePro**), exact model **`CS-CV206-C0-3B2WFR-Pro`** (Hi3518EV200, 16 MB SPI flash, Marvell SD8801 Wi-Fi, JXF22 MIPI sensor, 2.4 GHz Wi-Fi, microSD slot), based on [OpenIPC](https://github.com/OpenIPC/firmware).
Free from Ezviz cloud and telemetry, GPL-2.0-or-later.
Other variants of the CS-CV206 (for example `C0-1A1WFR`) have different hardware and are **not** covered; check yours before flashing anything.

## Features

- Video: H.264 up to 1080p over **RTSP**, JPEG snapshots, MJPEG, basic **ONVIF** support
- **Web page** (port 80, login): live picture, status, settings for stream, day/night (IR-cut filter and IR lamp), recording, audio, Wi-Fi, SIP; settings backup and restore, diagnostics
- **Audio**: microphone, speaker, two-way audio (ONVIF back-channel), **SIP intercom** (the reset button calls a softphone)
- **Recording** to a FAT32 microSD card, continuous or on motion, with play, seek and download from the page
- Setup: first start = own Wi-Fi network (`cv206-XXXX`) and a page to set the password and your network; reset button (hold 5 s) starts over; status LED
- Privacy: no outgoing traffic except time sync (NTP) and what you configure; every service needs the login

## Quick start

1. Read [INSTALL.md](INSTALL.md); you need a 3.3 V USB-UART adapter on the camera's UART pads (or an SD card for the fast route), Python 3 and `lrzsz` on a Linux PC.
2. Make the backup: `./flash_dump.py -p /dev/ttyUSB0 --include-cfg all`, then `./flash_dump.py --assemble` (keep `dump/` private).
3. Get the images: build them ([BUILDING.md](BUILDING.md); about a day for the first OpenIPC build) and write `sys` and `app` (and the same two images into slot B) with `./flash_write.py` (CRC-checked), then set the boot command once.
4. First start: join `cv206-XXXX` (password `cv206setup`), open `http://192.168.4.1`, set a password and your Wi-Fi network. Video: `rtsp://CAMERA/stream=0`.
   **Login:** there is a single account, user **`root`**, with the password you set on the page. It is used for the web page, RTSP, ONVIF and the HTTP endpoints on port 8080, and for calls into the SIP intercom.
   Until a password is set the page is open and everything else is closed. If you forget it, hold the reset button for 5 seconds (this also deletes the other settings).
5. Later updates: upload `app-….sqsh` on the page (System, Firmware update; about a minute), or from the PC with `tools/wupdate.sh app app.sqsh`.

If your OS supports it (Windows 7 apparently doesn't) you can use openipc.local address to find camera that is using DHCP.

## Safety

The install writes the firmware twice: slot A (used) and slot B (a known-good copy; the bootloader repairs slot A from it).
The Ezviz firmware is then no longer in the flash: it only exists in your backup, so **make and verify a backup first**.
The bootloader, device identity and stock configuration are never written. Even so, flashing can brick a device.
The SPI-programmer route (using clip is always sketchy in my opinion and chip should desoldered) and a clean-machine rebuild were not tested yet. Use at your own risk.

## Documents

| File | What |
|---|---|
| [INSTALL.md](INSTALL.md) | install on your camera: backup, UART and SD-card routes (SPI programmer: untested), first start, going back to stock |
| [BUILDING.md](BUILDING.md) | build the kernel and app images yourself (they contain parts that cannot be redistributed) |
| [LICENSE](LICENSE), [THIRD-PARTY.md](THIRD-PARTY.md) | license, licenses of everything else in the images (`majestic`, vendor libraries, Wi-Fi firmware, ...) |

## Third-party and proprietary code

`majestic` (OpenIPC's closed streamer, free for non-commercial use under the Prosperity license), the HiSilicon media modules, and Marvell's Wi-Fi firmware are proprietary: you build or extract them from your own camera and OpenIPC build.
