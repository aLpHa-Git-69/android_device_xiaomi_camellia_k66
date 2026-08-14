# 🦊 OrangeFox Recovery for Xiaomi Redmi Note 10 5G (`camellia`)

[![Build Status](https://img.shields.io/github/actions/workflow/status/rwxrx-rx/fox-twrp-device-camellia/build.yaml?branch=fox_12.1&label=OrangeFox%20Build&style=for-the-badge&color=FF7F00)](https://github.com/rwxrx-rx/fox-twrp-device-camellia/actions)
![Android Version](https://img.shields.io/badge/Android-13-3DDC84?style=for-the-badge&logo=android&logoColor=white)
![OrangeFox](https://img.shields.io/badge/OrangeFox-12.1-FF7F00?style=for-the-badge)

---

An unofficial OrangeFox Recovery device tree for the **Xiaomi Redmi Note 10 5G** (`camellia`, MediaTek MT6833), featuring a dedicated fix to get the NVT touchscreen working properly in recovery mode.

---

## 📱 Compatibility & Tested Devices

| Features | Specifications |
| :--- | :--- |
| **Device** | Xiaomi Redmi Note 10 5G / POCO M3 Pro 5G |
| **Codename** | `camellia` |
| **SoC** | MediaTek MT6833 Dimensity 700 (7 nm) |
| **CPU** | Octa-core (2x2.2 GHz Cortex-A76 & 6x2.0 GHz Cortex-A55) |
| **GPU** | Mali-G57 MC2 |
| **Display** | 6.5" IPS LCD, 90Hz (1080 x 2400 pixels) |
| **Memory** | 4GB / 6GB / 8GB RAM |
| **Storage** | 64GB / 128GB / 256GB (UFS 2.2) |
| **Battery** | 5000 mAh (18W Fast Charging) |
| **Touch IC** | Novatek `NT36672C` |
| **Panel** | Tianma |

> **Note:** This recovery image is highly likely to work on sibling "camellian" devices (Redmi Note 10T 5G, Redmi Note 11 SE, POCO M3 Pro 5G), provided the bootloader is unlocked.

---

## 🐛 NVT Touchscreen Wake Fix Explained

A common bug on `camellia` devices with Novatek (NVT) touch panels is that the **touchscreen stops responding after the screen turns off** (via screen timeout or pressing the power button) and turns back on in recovery.

**The Cause:**
When the screen blanks, the NVT driver drops into a `wakeup-gesture` suspend mode. In a normal system boot, waking the device fires the `fb_notifier`, which calls `nvt_ts_resume` and kicks the driver back to normal touch reporting. However, in TWRP/OrangeFox, the recovery UI handles screen dimming by turning off the backlight directly, without writing to the framebuffer (`/sys/class/graphics/fb0/blank`). Because the framebuffer status never changes to `1` (blank), the NVT driver remains stuck in gesture mode and no touch events reach the recovery UI.

**The Solution:**
This device tree utilizes a custom background daemon (`nvt_touch_wake_watch.sh`) that continuously monitors the screen's backlight brightness node (`/sys/class/leds/lcd-backlight/brightness`) instead of the framebuffer. 
Whenever the script detects the screen waking up (brightness changing from `0` to `> 0`), it rapidly writes `4` then `0` to `fb0/blank`. This manually mimics the framebuffer toggle, successfully forcing the NVT driver to resume normal multi-touch reporting on every wake.

**⚡ Responsiveness Optimization:**
Initially, the polling method introduced a noticeable delay of a few seconds before the touch responded after waking. To eliminate this latency, the script has been optimized with aggressive polling intervals:
*   **Polling Interval:** Reduced to `0.1s` (from `0.5s`) so the daemon detects the screen wake almost instantly.
*   **Framebuffer Toggle Delay:** Reduced to `0.05s` (from `0.2s`) to speed up the `nvt_ts_resume` call without failing the driver hook.

Since this daemon only runs in the recovery environment, the slight increase in CPU activity from aggressive polling does not negatively impact overall battery life or system performance.

*(Note: These services are initialized from the `on boot` trigger in `init.touchwake.rc` to bypass SELinux `vendor_init` property read denials).*


---

## 🛠️ Automated Build (CI/CD)

You no longer need to download the massive Android source tree to build this recovery. This repository uses **GitHub Actions** to automatically compile OrangeFox.

1. Go to the **[Actions](../../actions)** tab in this repository.
2. Select **OrangeFox CI Build** on the left sidebar.
3. Click **Run workflow** -> **Run**.
4. Wait for the build to complete (usually takes ~30-45 minutes).
5. Download your compiled `OrangeFox-camellia.img` from the **Artifacts** section at the bottom of the build summary.

---

## 💻 Manual Local Build

If you prefer to build it locally on your own machine, follow these steps:

```bash
# 1. Setup working directory
mkdir OFRP_12.1 && cd OFRP_12.1

# 2. Sync OrangeFox Source
git clone [https://gitlab.com/OrangeFox/sync.git](https://gitlab.com/OrangeFox/sync.git)
bash sync/orangefox_sync.sh --branch 12.1 --path "$PWD"

# 3. Clone this device tree
git clone -b fox_12.1 [https://github.com/cristidclxvi/device_xiaomi_camellia-fox.git](https://github.com/cristidclxvi/device_xiaomi_camellia-fox.git) device/xiaomi/camellia

# 4. Initialize build environment
. build/envsetup.sh
export ALLOW_MISSING_DEPENDENCIES=true
export FOX_BUILD_DEVICE=camellia

# 5. Build
lunch twrp_camellia-eng
mka adbd bootimage recoveryimage

```
## 🤝 Credits

Huge thanks to the developers and projects that made this possible:

| Contributor / Project | Contribution |
| :--- | :--- |
| **[TWRP](https://github.com/TeamWin)** & **[OrangeFox](https://gitlab.com/OrangeFox)** | Base recovery source and platform |
| **[cristidclxvi](https://github.com/cristidclxvi/device_xiaomi_camellia-fox)** | NVT touchscreen wake fixes |
| **[cd-Crypton](https://github.com/cd-Crypton)** | Base work and development tools |
| **[that1](https://github.com/that1)** & **[azwhikaru](https://github.com/azwhikaru)** | Contributions and assistance |
