> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# GPIO, LEDs and buttons — ZX279128S / ZXHN H199A

Driver: `files/target/linux/armsr/files-6.6/drivers/gpio/gpio-zx279128.c`.
Recovered 2026-09-07 from two unencrypted vendor binaries. No datasheet, no
vendor GPL source.

## 2026-11-11: normal userspace and WPS integration

Radio activity LEDs use PCI identity, not PHY numbering: `14c3:7603` selects
`green:wlan2g` and `14c3:7663` selects `green:wlan5g`. The shipped hotplug hook
selects that radio's throughput trigger, so MT7603 loading first does not swap
the indicators. Green LAN follows `br-lan`; green WAN follows physical `eth3`.

The basic wpad package included the standard WPS button script while compiling
out WPS itself. The board now selects full `wpad-mbedtls`. The finished-image
validator checks the daemon's actual WPS ubus methods and status fields, not
just the existence of the button script. Pushbutton enrollment also requires
`option wps_pushbutton '1'` on the intended secured AP. Fresh disabled radios
remain disabled; the existing owner configuration needs that option on its
enabled WPA2 2.4 GHz AP when migrated. No PIN or label enrollment is enabled.

The standard enrollment handler remains unchanged. A board-specific short-WPS
release hook starts a background observer after that handler finishes. It
blinks only the confirmed green WPS LED while an AP reports `pbc_status=Active`,
then turns it off when enrollment ends or status cannot be established. It
uses one descriptor lock, bounded status subprocesses and a monotonic deadline;
repeated presses refresh a distinct request generation without competing LED
writers. Full status JSON and peer addresses are not logged. The image includes
and validates the exact util-linux flock and coreutils timeout executables;
BusyBox's installed variants do not provide the required options.

This observer covers short-button AP enrollment. The pinned hostapd has no ubus
WPS lifecycle event, so enrollment initiated separately through a control API
does not automatically start the observer. It does not drive the unresolved red
WPS channel or replace long-button supplicant enrollment. Tests cover terminal
states, deadline expiry, a stalled message bus and overlapping/repeated presses;
physical enrollment and indication still need normal-image qualification.

Reset retains OpenWrt's standard action: a release shorter than one second
reboots, while a hold of at least five seconds with a mounted overlay requests
factory reset. GPIO observation alone does not qualify those actions; back up
the test configuration before exercising reset on the integrated image.

## 2026-11-10: physical LED map and polarity corrected

The owner observed one channel at a time with all other declared channels held
high. The earlier vendor-table labels below were incorrect for this board.
Every positively identified indicator is **active low**:

| GPIO | Physical indicator |
|---|---|
| 8 | Power, green |
| 38 | Power, red |
| 12 | WAN, green |
| 10 | WAN, red |
| 49 | LAN, green |
| 51 | 2.4 GHz, green |
| 60 | 5 GHz, green |
| 50 | WPS, green |

GPIO 48 produced no visible change during blinking or isolated high/low tests.
The owner sees a faint red WPS light even with every declared channel high; it
also remains faint with GPIO 48 low. Its control is unresolved. The DTS now
exposes the eight confirmed channels and leaves GPIO 48 unclaimed.

The front-panel **LAN indicator is GPIO-driven**, contrary to the previous
claim. Physical observations establish pin/color/polarity; activity triggers
still require validation on the normal OpenWrt image. WiFi triggers must follow
the radio's PCI identity rather than assume that phy0 is always the same band.

Physical button inputs were also checked through temporary sysfs GPIO exports:
WPS drove GPIO 41 low for the owner's press and high on release; a separate
Reset press drove GPIO 39 low and high on release. The exports were removed
afterward. This verifies pins and polarity, while normal OpenWrt button events,
WPS actions and reset/restore behavior still need integrated testing.

GPIO51 and PCIe PERST53/55 share bank3. Read-only register snapshots with WiFi
unbound showed DIR `0x10ff`, INPUT `0xd0ae`, SET/CLR zero. Turning the 2G LED on
changed INPUT to `0xd0a6`; turning it off restored `0xd0ae`. Reset bits `0xa0`
remained high. These measurements do not support replaying reset bits through
the vendor-style SET/CLR read-modify-write sequence. A later `phy0tpt` repeat
survived 150 wired pings. One earlier whole-board hang remains unexplained;
neither the GPIO driver nor the LED trigger is established as its cause.

## 2026-09-08: buttons require polling

The original `gpio-keys` binding was not functional: each boot printed
`failed to get irq for gpio:-2` twice. The GPIO controller has no `to_irq`
implementation, and gpio-button-hotplug's interrupt-based probe skips a button
when that lookup fails. Device binding alone was not evidence of button events.

The DTS now uses `gpio-keys-polled` with a 20 ms interval, handled by the same
OpenWrt gpio-button-hotplug module. Pins and polarity are unchanged. A physical
button press/release still needs verification; the earlier claim that merely
binding both buttons proved them working was too strong.

## ✗ "The stock DTS declares no GPIO controller, so this needs reverse-engineering from scratch" — half right, and the wrong half was load-bearing

`README.md` said this for a long time and it discouraged anyone from starting.
The first clause is true: the stock DTS really has no `gpio` node, no `pinctrl`
node, and nothing else that is a GPIO controller under another name. The
conclusion drawn from it was wrong, for three reasons that were all sitting in
plain sight:

1. **The vendor's GPIO driver is hardcoded, not DT-driven**, so its absence from
   the DTS says nothing about its existence.
2. **Both binaries that implement it are on disk and unencrypted** — the
   bootloader (`h199a-firmware/mtd0-bootloader.bin`) and the stock kernel
   (`ref/stock-vmlinux.bin`), neither of which is inside the AES container that
   blocks `np.ko`/`switch.ko`.
3. **This project has been driving GPIOs correctly for months.**
   `pcie-zx279128.c` toggles PCIe PERST# on pins 53 and 55 through
   `0x94407000` with hand-rolled bank arithmetic. The controller base was
   already known-working in our own tree. (Since `db628f9` it goes through
   the gpio driver via the pcie nodes' `reset-gpios`; the register path
   survives only as the fallback for a DT without those properties.)

There is also a **`gpiotest` command in the vendor bootloader** —
`gpiotest dir [num] [in/out]`, `gpiotest value [num] [1/0]`,
`gpiotest gvalue [num]` — so any pin can be probed interactively from the `=> `
prompt with no reverse engineering at all. Reading the ten vendor-declared input
pins takes about a minute.

## The register map

Base **`0x94407000`**, six banks of sixteen pins, `0x40` apart. Span
`0x94407000`–`0x9440717f`. Pins **0–95**; the stock accessors reject anything
above `0x5f`.

```
bank      = pin >> 4
bank_base = 0x94407000 + bank * 0x40
bit       = BIT(pin & 15)
```

| offset | meaning |
|---|---|
| `+0x00` | direction — bit set = output, clear = input |
| `+0x14` | input level |
| `+0x18` | output set — write the bit to drive high |
| `+0x1c` | output clear — write the bit to drive low |

`+0x04`–`+0x10` and `+0x20`–`+0x3f` are never touched by either vendor binary.
There is no interrupt, pull or debounce register: the stock driver is four
functions and has no IRQ support, which is why this driver does not offer
`to_irq` either.

Both vendor binaries **read-modify-write** the set and clear registers rather
than writing a bare bit. This driver does the same.

**Corroboration, independent of the accessors:** a vendor strap-reading routine
hardcodes `[base+0x14]` bits 5/15 (pins 5, 15), `[base+0x94]` bits 11/13/14/15
(pins 43, 45, 46, 47) and `[base+0xd4]` bits 13/14 (pins 61, 62). `0x94` is
bank 2 + `0x14`; `0xd4` is bank 3 + `0x14`. The 16-pin/`0x40`-stride model
predicts those three addresses exactly.

**Where the base lives in each binary:** bootloader global at VA `0x47f41dc4`
(load base `0x47edf800`); stock kernel global at `0xc05c1aac` holding
`0xf0707000`, which the kernel's own `map_desc` iotable at `0xc059baf0` maps
from `pfn 0x94400`, i.e. PA `0x94407000`.

> ⚠️ `0x94404000` also appears in the bootloader in what looks like a direction
> write. That address is the **UART**, not GPIO. One early SPL routine really
> does use it as a GPIO direction base — a vendor bug, harmless only because the
> pins involved default to input. Do not copy it.

## Pin map

Buttons, from the stock kernel's own descriptor array at `0xc05d5124`:

| pin | function |
|---|---|
| **39** | **RESET** |
| **41** | **WPS** |

`GetKeyGPIO` (`0xc03dc648`) is `zte_gpio_get_value` followed by
`clz r0,r0; lsr r0,r0,#5` — it returns the **inverse** of the pin level, so both
buttons are **active low**.

Historical inferred LED labels from the descriptor array at `0xc05d571c`
(superseded by the physical observations above):

| pin | label in the vendor table |
|---|---|
| 38 | Power, colour 1 |
| 10 | Power, colour 2 |
| 51 | WAN, colour 1 |
| 12 | WAN, colour 2 |
| 60 | 2.4 GHz |
| 48 | 5 GHz |
| 49 | WPS, colour 1 |
| 50 | WPS, colour 2 |
| 8 | unlabelled — most likely LOS or Internet |

The earlier conclusion that the front LAN indicator was not GPIO-driven and
the assumption of active-high polarity were both wrong. Bootloader initial
levels alone did not establish the physical color/function mapping.

## Pins that must not be driven

| pins | why |
|---|---|
| 5, 15, 43, 45, 46, 47, 61, 62 | the 8-bit **board-ID strap**, read by `GetBoardType`. Safe to read, never drive. |
| 53, 55 | PCIe PERST#, taken by the pcie nodes' `reset-gpios` (gpiod) since `db628f9` |
| 52, 54 | vendor drives them low at boot and never touches them again; purpose undetermined, likely PHY or module resets |
| 39, 41 | buttons — inputs |

`bootsel` is **not** a GPIO despite appearing in the boot log next to them: it is
`(readl(0x94000040) >> 6) & 3` in CRM0.

## Pin muxing — deliberately not handled

Six registers at CRM2 `0x94200000 +0x00..0x14` are written verbatim from the
vendor board table before any GPIO use (`f3ffffa, effeff, 555ffff, 3dbf85, 0, 0`
on this board — the same values the stock kernel prints as its `%d,%x,%x`
table), with additional ORs to force the strap pins to GPIO.

Both a 1-bit-per-pin and a 2-bit-per-pin reading of those registers were tested
against the known-GPIO pin set and **both fail** — pins 52, 60, 61 and 62
contradict either model. It is a peripheral-function-select block whose layout
could not be recovered from these binaries.

Practical consequence: the bootloader has already programmed it by the time
Linux starts, so the gpiochip driver does not need to. But **a pin that is not
in the vendor's own list is not necessarily muxed to GPIO**, and sweeping all 96
pins blind would fight whatever peripheral currently owns them. Probe with
`gpiotest` from U-Boot instead.

## Bench note

`current_board` reads `0xc05b320c` on this unit, which indexes entry 6 (`e500`)
of the board table at `0xc05b2b1c`. Entry 7 is `h199a` and is byte-identical
except for GPIO 8's initial value. The pin array at `0xc05ba0b4` (48 entries,
stride `0x1c`) reproduces the boot log's input/output list exactly, which is how
the identification was confirmed.
