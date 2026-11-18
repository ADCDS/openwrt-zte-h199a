# Hardware validation and limits

All hardware results are from **one ZTE ZXHN H199A**. The software target is
OpenWrt 24.10-SNAPSHOT with Linux 6.6.151. Host tests check implementation
properties; they do not substitute for hardware qualification or establish
reliability on other routers.

## Bank-aware installation and upgrade qualification — 2026-11-18

The initial trials below used images 03 and 04. Fresh checks of the recreated
v1.0.0 assets are recorded separately below.

| Trial | Result |
|---|---|
| Stock A → OpenWrt B, stock web updater | Passed using the Python client, no source-bank override and zero UART bytes during upload; about 98 seconds |
| Stock B → OpenWrt A, stock web updater | Passed with the exact same container and client, no override and zero UART bytes during upload; about 98 seconds |
| Native image 03 → 04 upgrade on B | Changed rootfs, stayed B, incremented serial 4 → 5; all 13 original configuration/SSH-host-key hashes unchanged |
| Native image 03 → 04 upgrade on A | Changed rootfs, stayed A, incremented serial 4 → 5; same configuration/host-key preservation |
| Legacy A-only image on running B | `sysupgrade -T` refused it before shutdown/erase; boot identity and header hash unchanged |
| Bank A protection | Exactly mtd6/7/8/13 writable; compiled SPI policy matches the independent A model |
| Bank B protection | Exactly mtd9/10/13/14 writable; compiled SPI policy matches the independent B model |
| Payload and recovery | Active kernel/rootfs and header CRCs matched; peer stock firmware and protected boot/calibration data were read back and compared |
| Earlier image-04 final check | Default kernel restored in A; original stock B, configuration and host keys retained; WAN DHCP and UBIFS up; onboard 2.4 GHz association, ten pings with zero loss and LuCI access passed |

UART was used for controlled source-bank setup and boot observation. The web
uploads themselves sent no UART commands. This does not provide a stock-web
backup/extraction method for another unit's header and calibration.

### Recreated v1.0.0 assets — 2026-11-18

The production image was rebuilt from the reviewed release sources with image
ID `v1.0.0`. Image/profile, rootfs and calibration checks passed. ROM inspection
found no lab Wi-Fi keys, generated SSH host keys or authorized keys.

| Fresh trial | Result |
|---|---|
| Stock A → release OpenWrt B | Same released web container; 98.56 seconds, no source override, zero UART bytes during upload |
| Stock B → release OpenWrt A | Same container; 98.92 seconds, no override, zero UART bytes during upload |
| Native A, image 04 → v1.0.0 | Changed payload, remained A, serial 7 → 8 |
| Native B, v1.0.0 → v1.0.0 | Exact released native archive, same-payload reinstall, remained B, serial 4 → 5; earlier changed-payload B trial is listed above |
| Flash protection and contents | Both banks' MTD flags and independent SPI policies matched; active kernel/rootfs hashes, header CRCs, protected boot/calibration and whole stock peer matched |
| Configuration | All 13 original configuration and SSH-host-key hashes retained after native upgrades and at final return to A |
| Final state | v1.0.0 in A, original stock B; UBIFS and WAN DHCP up; onboard 2.4 GHz association, ten zero-loss pings and LuCI access passed |

The onboard PC adapter was restored to NetworkManager; the USB Internet
adapter and its default route were preserved. These checks add no fresh
power-cut, throughput, long-duration or 5 GHz reliability qualification.

## Earlier production measurements — 2026-11-15 to 2026-11-17

These results belong to the images tested then. They were not all rerun on the
bank-aware release and do not add to its boot-reliability sample.

| Test | Recorded result |
|---|---|
| Earlier A-only NAND boot sample | 5/5: three cold, one warm, one after sysupgrade |
| LAN/WAN | WAN DHCP and exact bidirectional transfers through NAT; all three LAN jacks were exercised on an earlier production image |
| Wired NAT, software flow offload disabled | 360.2 Mbit/s toward WAN / 307.1 from WAN |
| Wired NAT, software flow offload enabled | 378.7 / 375.7 Mbit/s; this was an explicit lab setting, not proof of a clean-install default |
| 2.4 GHz AP through NAT | 44.5 / 58.3 Mbit/s with a real associated client and zero measured ping loss |
| Watchdog | CPU0 expiry produced a whole-board reset; procd ownership, magic close, reboot and orderly poweroff checked; CARDRESET cannot be reported |
| Buttons and LEDs | Physical GPIO transitions and earlier indicator behavior observed; latest integrated WPS/reset/indicator actions need repeat testing |
| Earlier A-only upgrade/recovery drills | Configuration-preserving upgrades, a controlled power cut and header-invalidation/reinstall drills passed; stock synchronization complicates fallback |
| Datapath recovery | Manual diagnostic reset restored traffic, and an induced IRQ stall recovered after the first-stage NAPI/watchdog kick |

Short throughput transfers do not establish sustained, mixed-load or
full-duplex performance. A workload's CPU limit does not mean SMP is disabled.

## 5 GHz: bounded operation, failed reliability

Image 03 in bank B enumerated MT7663 with AP firmware V2/N9 `7663mp1827`.
An onboard ath10k PCI client associated using WPA2 on channel 149, VHT80,
AP TX power 10 dBm. Ten pings passed with zero loss. Separate 20-second local
transfers measured **278.7 Mbit/s client → router** and **289.7 Mbit/s router →
client**. These are local AP figures, not NAT measurements.

About 33 seconds after the download ended, IRQ status became `0xffffffff` and
the guard stopped recovery. Root-port command, bus numbers and bridge windows
lost configuration while IDs/BARs persisted; endpoint accessibility was lost.
AER showed flow-control protocol/completion-timeout errors, replay errors and
a first-error pointer of 13. There was no preceding MCU recovery or Ethernet
reset log. A complete pre-AP AER baseline was not captured in that trial.

Independent stock-log review found a healthy port-0 L0/BAR capture and later
stock A/B captures where its L0 wait did not succeed and its BARs were absent,
while port 1 initialized. That is stronger evidence than absence of generic
PCI ID strings, which stock does not print in either case.

Private traced kernels matched all six decoded VID6 mux words and GPIO52–55
settings. Held PERST, a 120-second power-off with UART TX low, VID1 analog
settings, an after-clocks reset pulse, and training stopped during generic RC
setup did not establish a fix. The traced boots never obtained a healthy
5 GHz endpoint, so they did not reproduce the runtime fault or prove absence
of CPU writes during it. Raw LTSSM `0x2` is recorded without asserting a vendor
receiver-detection mapping.

The radio is **not repaired**. Physical supply/refclock and UART back-power or
strap effects remain unmeasured; permanent board damage is not established.
Client power-save-off and port-0-only noncoherent-DMA comparisons remain
untested because the endpoint was unavailable. See [WIFI.md](docs/WIFI.md)
and the optional [diagnostic artifacts](tools/diagnostics/README.md).

## Outstanding acceptance

- Fresh power-cut qualification of this bank-aware image, including a verified
  bootable peer and the stock synchronization behavior.
- Latest-image LAN2/LAN3, integrated LEDs/WPS/reset actions, destructive factory
  reset, extended mixed-load and full-duplex testing.
- Automatic full datapath reset after a genuine persistent stall. A manual
  reset and the first-stage kick are not proof of that trigger.
- Working production per-flow hardware offload. Some table/default-flow
  experiments have positive results; exact-match flow acceleration has not
  been demonstrated. See [PP-OFFLOAD.md](docs/PP-OFFLOAD.md).
- Generalization beyond the single unit and supported stock-firmware extraction
  version. First installation still requires own-unit backup and UBI-window
  preflight; the marker guard is not an all-bytes-erased test.

## Host-side checks

The recreated release checkout's CI ran **677 tests, with 151 skipped** because
some cases require private bench inputs or optional artifacts. The separate
diagnostic checker passed **13 actual-C success/fault cases**. Documentation
checks covered all 54 Markdown files without missing local links/anchors and
parsed all 14 binding YAML files. YAML parsing is not dt-schema qualification.
The earlier complete development run passed 677 tests without skips.

Private raw UART, stock captures, calibration and Wi-Fi keys are not published.
The public repository preserves source, bounded results and explicitly marked
historical investigations.
