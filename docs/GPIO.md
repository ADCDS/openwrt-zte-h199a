# GPIO, LEDs and buttons — ZX279128S / ZXHN H199A

Current status, **2026-11-18**: the GPIO driver, eight confirmed LED channels,
polled Reset/WPS inputs and WPS observer are integrated. Physical LED mapping
and button pin levels were checked on an earlier image. End-to-end LED,
WPS-enrollment and Reset/factory-reset behavior remains unqualified on the
release image; see [VALIDATION.md](../VALIDATION.md).

The implementation is
[`gpio-zx279128.c`](../files/target/linux/armsr/files-6.6/drivers/gpio/gpio-zx279128.c),
with the board wiring in
[`zx279128s-zte-h199a.dts`](../files/target/linux/armsr/files-6.6/arch/arm/boot/dts/zte/zx279128s-zte-h199a.dts).
Its register interface was recovered from the vendor bootloader and stock
kernel, without a public datasheet or vendor driver source.

## Confirmed board wiring

All eight positively identified indicator channels are **active low**. The
owner observed each channel separately on 2026-11-10, superseding the earlier
inferred vendor-table labels.

| GPIO | Indicator | Linux LED name |
|---|---|---|
| 8 | Power, green | `green:power` |
| 38 | Power, red | `red:power` |
| 12 | WAN, green | `green:wan` |
| 10 | WAN, red | `red:wan` |
| 49 | LAN, green | `green:lan` |
| 51 | 2.4 GHz, green | `green:wlan2g` |
| 60 | 5 GHz, green | `green:wlan5g` |
| 50 | WPS, green | `green:wps` |

GPIO48 produced no visible change during isolated high/low and blinking tests.
A faint red WPS light remained visible with all declared channels high and
also with GPIO48 low. That channel's control is unresolved, so the DTS leaves
GPIO48 unclaimed. The front-panel LAN indicator is GPIO-driven.

| GPIO | Button | Polarity |
|---|---|---|
| 39 | Reset | Active low |
| 41 | WPS | Active low |

Temporary GPIO observations confirmed low on each physical press and high on
release, then the exports were removed. The DTS uses `gpio-keys-polled` with
a **20 ms** interval through OpenWrt's gpio-button-hotplug implementation.
Interrupt-based `gpio-keys` does not work with this driver because it provides
no `to_irq` operation. Registering the inputs alone does not qualify their
normal OpenWrt actions.

## Activity LEDs and WPS

[`01_leds`](../files/target/linux/armsr/base-files/etc/board.d/01_leds) assigns
green LAN activity to `br-lan` and green WAN activity to physical `eth3`.
[`10-zx-wifi-leds`](../files/target/linux/armsr/base-files/etc/hotplug.d/ieee80211/10-zx-wifi-leds)
identifies each radio by PCI vendor/device ID: `14c3:7603` selects
`green:wlan2g`, and `14c3:7663` selects `green:wlan5g`. It binds the discovered
PHY's throughput trigger and briefly retries if trigger registration follows
the wiphy event. PHY numbering is not a stable band identifier.

The image selects full `wpad-mbedtls`, with WPS support. AP pushbutton
enrollment also requires `option wps_pushbutton '1'` on the intended secured
AP. Fresh disabled radios remain disabled. No label/PIN enrollment is enabled
by the board integration.

The standard OpenWrt enrollment handler remains responsible for WPS. On a WPS
release shorter than three seconds,
[`50-h199a-wps-led`](../files/target/linux/armsr/base-files/etc/hotplug.d/button/50-h199a-wps-led)
starts the background
[`h199a-wps-led`](../files/target/linux/armsr/base-files/usr/libexec/h199a-wps-led)
observer. It queries `hostapd.*` `wps_status` and blinks only the green WPS LED
while `pbc_status` is `Active`; it clears the LED when enrollment ends or
status cannot be established. Bounded subprocesses, a descriptor lock and a
monotonic deadline limit the observer. Repeated presses refresh its request
generation without competing LED writers. It does not log status JSON or
peer addresses.

This observer covers short-button AP enrollment. The pinned hostapd supplies
no WPS lifecycle ubus event, so an enrollment begun separately through a
control API does not automatically start it. It does not replace long-button
supplicant enrollment or drive the unresolved red WPS channel. The image
includes the required `/usr/bin/util-linux-flock` and
`/usr/libexec/timeout-coreutils`; the build validator checks these actual
executables and WPS ubus support. Host tests cover terminal states, deadlines,
a stalled bus and repeated/overlapping presses. Physical enrollment and its
indication still need qualification on the release image.

Reset retains OpenWrt's standard action: a release shorter than one second
requests reboot; a hold of at least five seconds with a mounted overlay requests
factory reset. Back up the configuration before testing these actions.
Observed GPIO transitions do not establish that either action has passed.

## Register interface and driver behavior

The controller spans `0x94407000`–`0x9440717f`: six banks of 16 pins, 96 pins
total, with a `0x40` bank stride.

```text
bank      = pin >> 4
bank_base = 0x94407000 + bank * 0x40
bit       = 1 << (pin & 15)
```

| Bank offset | Known use |
|---|---|
| `+0x00` | Direction: set bit = output; clear bit = input |
| `+0x14` | Input level |
| `+0x18` | Output set: drive high |
| `+0x1c` | Output clear: drive low |

The recovered vendor accessors do not use the other offsets. They provide no
evidence for an IRQ, pull or debounce interface; this driver exposes none.
Both vendor binaries read-modify-write SET/CLR, and this driver follows that
sequence under an IRQ-safe spinlock. It writes the desired output value before
switching direction. GPIO numbering is allocated dynamically in Linux; board
consumers use DT descriptors rather than fixed sysfs GPIO numbers.

GPIO51 and PERST GPIO53/55 share bank 3. Earlier read-only snapshots showed
SET/CLR reading zero. Turning the 2.4 GHz LED on changed the observed input
word from `0xd0ae` to `0xd0a6`; turning it off restored it, while the reset bits
`0xa0` remained high. This did not support a claim that the SET/CLR sequence
replays reset bits. A prior unexplained board hang does not establish a GPIO
driver or LED-trigger cause.

The GPIO register clock is obtained through
`devm_clk_get_optional_enabled()`. The CRM provider keeps it enabled as a
critical clock; the optional lookup preserves compatibility with older DTs.

## Reserved pins and mux state

| Pins | Current use and constraint |
|---|---|
| 5, 15, 43, 45, 46, 47, 61, 62 | Board-ID strap inputs; do not drive |
| 53, 55 | PCIe PERST lines owned by `reset-gpios`; do not manipulate separately |
| 52, 54 | Vendor initializes them low as outputs; purpose unresolved |
| 39, 41 | Button inputs |

The release DTS assigns GPIO53 to PCIe port 0 and GPIO55 to port 1. Vendor
disassembly establishes both reset pins, but their physical slot assignment
has not been electrically traced; the vendor pulses both before scanning.
The nearby `bootsel` value is a CRM field, `(readl(0x94000040) >> 6) & 3`,
rather than a GPIO.

Pin muxing is separate from this gpiochip, in six CRM2 words at
`0x94200000 + 0x00..0x14`. The decoded VID6 table and the November 18 snapshot
matched:

```text
0f3ffffa 00effeff 0555ffff 003dbf85 00000000 00000000
```

GPIO52/54 were low and GPIO53/55 high, all outputs. The GPIO driver does not
rewrite the mux. A complete per-pin mux encoding has not been established, so
unlisted pins must not be assumed to be GPIO or swept blindly. A matching
register snapshot does not verify the board's physical clock, supply or
reset-waveform integrity; see the current [Wi-Fi investigation](WIFI.md).

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/GPIO-BRINGUP.md). They are not current installation instructions.
