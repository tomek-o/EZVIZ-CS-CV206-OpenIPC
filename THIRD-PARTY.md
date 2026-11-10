# Third-party components and licensing

The code from this project (this repository) is **GPL-2.0-or-later** (`LICENSE`). The firmware images contain many components that are not part of this project; this file lists them.
Compiled 2026-11-10 from the OpenIPC build tree, OpenIPC's published pages and the binaries. It is not legal advice; "not verified" means exactly that.

**My decision:** I distribute the finished binaries non-commercially and on my own responsibility, although the status of some parts is not fully clear. The repository itself holds sources, scripts and documents only; the images are a separate package (last section).

## Components

| Component | License | Redistribution and notes |
|---|---|---|
| **`majestic`** streamer (`/app/usr/bin/majestic`, binary only) | Prosperity Public License 3.0.0 | non-commercial sharing with notices only (below) |
| HiSilicon MPP libraries and kernel modules (vendor binaries from the OpenIPC build; a few modules are open OpenIPC replacements) | proprietary | terms not found, **not verified** |
| **Marvell SD8801 Wi-Fi firmware** 14.85.36.p104 (inside `sys`) | Marvell licence, `licenses/LICENCE.Marvell`: binary redistribution with the notice, only with Marvell chips, no reverse engineering | **unclear for this build**: `linux-firmware` ships another build (14.68.36.p204) under that licence, mine comes from the Ezviz image; cleaner option, not done: build `sys` with the `linux-firmware` blob after testing it |
| Linux 4.9.37 (OpenIPC branch) + patches, BusyBox 1.36.1, wireless tools | GPL-2.0 | yes; the source package contains the source |
| wpa_supplicant 2.10 (AP support enabled) | BSD-3-Clause | yes |
| musl, json-c, libyaml | MIT | yes |
| libevent, libopus, libogg | BSD-3-Clause | yes |
| mbed TLS 3.6.4 | Apache-2.0 | yes |
| zlib 1.3.1 | zlib | yes |
| Ubuntu Mono subset ("OpenIPC Mono") | Ubuntu Font Licence 1.0 | yes, the licence file travels with it (`licenses/Ubuntu-Font-Licence-1.0.txt`; in the image from build 15:08 of 2026-11-10 on) |
| `yaml-cli`, `ipcinfo` (OpenIPC utilities) | licence not verified | **not verified** |
| OpenIPC firmware tree / Buildroot | MIT / GPL-2.0 | build only, not in the images; snapshot in the source package |
| Ezviz stock firmware | proprietary | never published; only in my private flash dump (no longer in the camera's flash) |

## `majestic`

- **License:** the Prosperity Public License 3.0.0 (<https://github.com/OpenIPC/majestic/blob/master/LICENSE.md>, contributor OpenIPC (c) 2025): free for **non-commercial** use and sharing, commercial use only as a **30-day trial**; everyone who gets a copy must also get the license text and the contributor and source lines.
  OpenIPC's pages (<https://openipc.org/business>, <https://openipc.org/partners>) say the binary is distributed under that license and that commercial terms (a licence to "sell, flash, bundle or run Majestic commercially") are available through their partner program.
  Not stated anywhere I looked: whether a third party may publish a free image containing the binary. The license text reads as allowing non-commercial sharing with the notices.
- **What I do:** the repository does not contain `majestic` (it comes from the OpenIPC build); the package ships the license text and the notices; non-commercial use only. Nobody should sell this firmware, ship it on devices for sale, or run it in a commercial service.
- **Activation ("OpenIPC Pro"):** the binary contains an entitlement client for an OpenIPC portal (`devices.activate.openipc.org`, `/api/v1/licence`). On my camera the state is `none`: nothing linked, no renewal scheduled, no outgoing connection (the cipher module is not loaded).
  The only feature I found it gates is encrypted recordings (`records.encryption: pubkey`); the purpose of a `mark` setting is unknown (I have never seen a mark on my pictures). I do not link or activate anything and use no Pro feature; whether to ever do so is undecided, since it would identify the camera to OpenIPC.

## Distribution package

`tools/make-distribution.sh` builds two archives in `_release/` (not in git; it publishes nothing):
- `cv206-open-firmware-VERSION.tar.xz`: the `sys` and `app` images, checksums, `README.txt` (use at my own risk without warranty, non-commercial only, the one supported model, no affiliation, removal on a justified request), `INSTALL.md`, this file and `licenses/` (Prosperity text, Marvell licence, font licence, GPL-2.0).
- `cv206-open-firmware-VERSION-source.tar.xz`: the corresponding source of the GPL parts (the exact kernel tarball, BusyBox, wireless tools), this repository, and the OpenIPC build tree snapshot (commit `ba8647a`), so no written source offer is needed.
- **Privacy gate:** `tools/scan-images.py` unpacks the app image and every XZ stream of the kernel (including the initramfs) and looks for my secrets, the camera's identifiers from my dump, MAC-like strings, e-mail addresses, home paths and the builder's user and host name (the kernel is built as `cv206@build`, set in `tools/kbuild.sh`). Development builds are refused (they bake test credentials in).
- **Risks I accept:** `majestic`'s non-commercial terms and unclear status for images, the unclear terms of the HiSilicon binaries and of the exact Marvell build. I will remove anything on a justified request of the rights holder.
