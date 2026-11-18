# Wi-Fi — ZX279128S / ZXHN H199A

Current status, **2026-11-18**: the MT7603 2.4 GHz AP works with the owner's
stock calibration base and the radio's own OTP trims. The MT7663/MT7613BE
5 GHz radio has carried verified traffic, but later loses PCIe accessibility
and can fail link training on subsequent boots. Keep 5 GHz disabled for normal
use. These results come from one H199A; see [VALIDATION.md](../VALIDATION.md).

## Radios and driver integration

| Radio | PCI identity | Host port | Driver | Calibration and MAC |
|---|---|---|---|---|
| 2.4 GHz MT7603E | `14c3:7603`, observed at `0001:01:00.0` | 1 | `mt7603e` | Own-stock 512-byte base plus own-chip OTP; factory MAC from `tag` record 0 |
| 5 GHz MT7613BE / MT7663 family | `14c3:7663`, observed at `0000:01:00.0` | 0 | `mt7615e` | `wifi` MTD partition at `+0x20000`; factory MAC from `tag` record 1 |

PHY indices and UCI names such as `radio0` depend on discovery and module order.
Identify a radio by its PCI device and path before changing its configuration.
The shipped activity-LED hook also uses PCI identity; see [GPIO.md](GPIO.md).

The host driver is
[`pcie-zx279128.c`](../files/target/linux/armsr/files-6.6/drivers/pci/controller/dwc/pcie-zx279128.c),
using the Synopsys DesignWare framework, legacy iATU and INTx interrupts.
Both ports are described in the
[board DTS](../files/target/linux/armsr/files-6.6/arch/arm/boot/dts/zte/zx279128s-zte-h199a.dts)
with Gen1 limits and coherent DMA. Port 0 uses DBI `0x0f000000` and glue
`0x09500000`; port 1 uses DBI `0x0f100000` and glue `0x09600000`.
The shared clock/reset sequence and both PERST operations precede bus scans.
The historical claim that port 1's glue address was wrong was a false negative
from reading that block before enabling its clock.

## Supply the 2.4 GHz calibration when building

The MT7603 OTP contains sparse factory trim data, rather than a complete base
EEPROM. The earlier empty-eFuse conclusion was withdrawn. The supported stock
firmware supplies `/etc/Wireless/MT7603e/MT7603E_EEPROM.bin`, a 512-byte base;
mt76 merges the radio's eight factory trim bytes into it. The base SHA256 is
`c2c0f5acfc78f63edb6b9b2b1dea95f03274b4b489769344be9380d0cde88cc5`.
Displayed TX power alone does not qualify RF calibration or range.

Extract the base offline from your own corrected stock kernel and filesystem
backups. From the repository root:

```sh
python3 tools/extract-stock-calibration.py \
  /private/stock-kernel-b-ecc.bin /private/stock-rootfs-b-ecc.bin \
  /private/h199a-original-calibration
```

[`extract-stock-calibration.py`](../tools/extract-stock-calibration.py) accepts
the identified July 2021 firmware only. It requires Python 3 and OpenSSL
libcrypto, validates the kernel, decrypted filesystem and JFFS2 CRCs, and
requires a new output directory. A completed extraction includes
`verification.json`. Keep the extracted vendor files with your private backups.
The source tree contains no extracted stock firmware, calibration file or
decryption key. The separately published bench-reference firmware embeds the
bench calibration; it is not a substitute for another unit's own inputs.

For an installable production image, use your own header template as described
in [INSTALL.md](INSTALL.md):

```sh
BOOT_PROFILE=production JOBS=2 \
H199A_HEADER=/private/header-template.bin \
H199A_MT7603_EEPROM=/private/h199a-original-calibration/MT7603E_EEPROM.bin \
./build.sh
```

Install the host `device-tree-compiler` package for `fdtget`; build prerequisites
are covered in the [repository README](../README.md).
[`h199a-calibration.py`](../tools/h199a-calibration.py) checks the base length,
chip ID and qualified hash before source preparation. It generates a private
include in the ignored OpenWrt build tree, supplying `mediatek,eeprom-data`
to `wifi2g`; the DTS requests the native `mediatek,eeprom-merge-otp` path.
Do not pad the file or merge OTP in userspace.

Normal and production builds require this input. Diagnostic builds may omit it
for non-radio work. The build clears stale generated calibration when inputs
or profiles change. Final checks verify the compiled DTB's exact bytes and
merge property, its presence in the packaged kernel, and wrapper CRCs. A
companion `*-calibration.json` records calibration, DTB and image hashes.
The resulting image contains the owner-supplied base.

## Configure and verify the 2.4 GHz AP

Fresh OpenWrt radios are disabled until configured. Existing installations
should retain their working wireless configuration. Use LuCI's **Network →
Wireless** page to configure the MT7603 2.4 GHz device: set the actual country,
choose the SSID and WPA2 security, and attach the AP to LAN. Keep the 5 GHz
device disabled. Do not enable both radios by copying an old `radio0` example.

These read-only commands show the registered radio identities without printing
wireless passwords:

```sh
for phy in /sys/class/ieee80211/*; do
  [ -r "$phy/device/device" ] || continue
  printf '%s vendor=%s device=%s path=%s\n' "${phy##*/}" \
    "$(cat "$phy/device/vendor")" "$(cat "$phy/device/device")" \
    "$(readlink -f "$phy/device")"
done
uci -q show wireless | sed -n '/=wifi-device$/p; /\.path=/p; /\.band=/p; /\.disabled=/p'
iw dev
```

Match the UCI device's path to the registered PCI device; `14c3:7603` is the
2.4 GHz radio. If the endpoint is absent, loading its module successfully does
not establish that the radio exists or works. The shipped build uses normal
package autoload; the former `zx-wifi-late` overrides are retired.

For acceptance, have an independent client associate, obtain a DHCP lease,
reach LuCI and exchange data in both directions. Confirm the AP interface and
associated station with `iw dev` and `iw dev <ap-interface> station dump`.
Use measured transferred bytes and elapsed time for goodput, rather than the
negotiated link rate. The bench unit measured 44.5 Mbit/s toward WAN and
58.3 Mbit/s from WAN through its 2.4 GHz AP in short NAT tests. On the fresh
v1.0.0 image in A, the onboard PCI client associated at 2437 MHz, passed ten pings with
zero loss and reached LuCI. Longer-duration reliability remains unqualified.

## 5 GHz: traffic passed, reliability failed

On 2026-11-18 the default bank-aware production kernel booted in bank B with
the MT7663 present. The PC's onboard ath10k PCI client associated using WPA2,
channel 149 and VHT80, with AP TX power 10 dBm. Ten pings had zero loss.
Separate 20-second local transfers measured **278.7 Mbit/s client-to-router**
and **289.7 Mbit/s router-to-client**. These are local AP tests, not NAT figures.
The owner's USB Internet adapter was not used or reconfigured.

The installed radio firmware was the **MT7663 AP V2** package,
`mt7663pr2h_rebb.bin` plus `mt7663_n9_rebb.bin`, reporting N9 version
`7663mp1827`. A source API name such as `sta_update_ops` is not evidence that
the installed blob is station-only firmware.

About 33 seconds after the download ended, the driver reported
`invalid interrupt status: 0xffffffff; device recovery stopped`.
Root-port COMMAND, bus numbers and bridge windows lost configuration; root IDs
and BAR0/BAR1 retained their values. Glue initially still reported L0, then
raw LTSSM state `0x2`; endpoint configuration reads became all ones.
AER recorded uncorrectable `0x6000` (flow-control protocol and completion
timeout), correctable `0x9100` (replay errors/header-log overflow), and first-error
pointer 13 (flow control). There was no complete pre-AP AER baseline, so some
latched errors may predate the transfer.

No preceding MCU-timeout/recovery or Ethernet datapath-reset log was observed.
ASPM, L1 substates and mt76 runtime PM were disabled. The evidence establishes
loss of PCIe/controller configuration and accessibility. It does not establish
the underlying electrical or software trigger, a thermal cause, or permanent
board damage.

The shipped
[`990-dma-invalid-index-fail-stop.patch`](../files/package/kernel/mt76/patches/990-dma-invalid-index-fail-stop.patch)
rejects invalid full-width DMA indices and inaccessible MT7615 interrupt status
before they can corrupt ring ownership or drive unsafe recovery. It drains
software producers during teardown; where DMA stop cannot be verified, it
quarantines DMA-visible allocations until reboot and denies reprobe at that
device identity. This contains a failure; it does not repair the PCIe link.
The shared module layouts changed, so rebuild and install the matching image
instead of mixing these modules with an older rootfs.

## Boot failures and diagnostic controls

Subsequent normal and traced boots could not obtain a healthy port-0 endpoint.
A passive baseline showed raw LTSSM `0x2`, no endpoint and zero AER status,
while root command and bridge configuration remained programmed. That startup
failure differs from the later configuration-loss event. Only `0x11 = L0` has
been established from the vendor code; do not label `0x2` with an unverified
vendor receiver-detect state name.

The healthy stock-A capture `web-a-to-b-03-retry2` reports port 0 L0/Gen1 at
count 1 and assigns all three endpoint BARs. Later stock-A and stock-B captures
enter the port-0 L0 wait without its success or BAR messages, while port 1
reaches L0 and receives its BAR. The stock comparison uses these link/BAR
messages, not generic PCI ID text. `stock-a-debug-window` is a failed capture.
This reproduces port-0 initialization failure under stock firmware without
distinguishing retained state, signal integrity, supply margin or initialization
behavior. Private raw captures are not part of the release.

All six CRM2 mux words and GPIO52–55 directions/levels matched the decoded
VID6 stock settings. GPIO52/54 were low and GPIO53/55 high, all outputs.
Register readbacks do not measure reference-clock or supply integrity. These
private controls did not establish a fix:

- Holding PERST through shared initialization, and 120 seconds powered off
  with UART TX low.
- Applying and reading back the stock VID1 analog branch on this VID6 unit:
  `0x0046c24a` and `0x00202d5a` at the port-0 SerDes registers.
- Stopping both LTSSMs, holding both existing PERST lines low for 100 ms after
  clock setup, releasing for 200 ms, and retraining before either host was
  published. The missing-link mask remained `0x1`.
- Holding only port 0's LTSSM off during generic DWC root-complex setup, then
  enabling it through `start_link`. The intended path ran with CTRL `0x8`,
  port-link control `0x00010120` and width/speed control `0x0002012c`; its link
  wait still timed out.

The optional observer and two alternative experiment patches are documented in
[tools/diagnostics](../tools/diagnostics/README.md). `build.sh` does not apply
them. The observer validated nonzero DWC DBI-helper and root PCI configuration
write counts, including standard PM capability writes. **No traced boot had a
healthy 5 GHz endpoint**, so the tracer never captured the earlier runtime
failure and cannot establish absence of CPU writes at that event. Its bounded
ring records write intentions, not accepted hardware values; direct MMIO,
DBI2, DMA and reset/clock paths are outside its coverage.

## Remaining work and final bench state

The next useful isolation step is a physical disconnect of both router DC
power and UART, or measurement of the actual supply and reference clock.
The UART and Internet adapters share an xHCI controller, and their USB2 hub
reports no power switching. No USB power or controller-reset action was
attempted. A prior combined DC/UART disconnect restored operation once; it did
not identify which connection or retained state mattered.

Client station power save remains a separate untested control. Disabling mt76
runtime PM does not disable the client's 802.11 PS behavior in AP firmware.
On the next healthy link, record the test client's state, disable PS before
association, verify it after association/traffic, and compare the same traffic
and idle periods. A private port-0-only noncoherent-DMA comparison also remains
untested. Stock explicitly selects coherent DMA for both radios, and initial
link training precedes DMA.

The router was restored to the recreated production v1.0.0 in bank A, Linux
6.6.151, with 2.4 GHz, WAN, SSH and LuCI working. The original wireless
configuration and configuration/host-key hashes were retained, with 5 GHz
disabled; original stock bank B was preserved. The onboard test client was
restored and the USB Internet adapter was untouched.

Earlier hypotheses and tests are historical records in
[WIFI-JOURNAL.md](WIFI-JOURNAL.md). Use the current acceptance matrix in
[VALIDATION.md](../VALIDATION.md) when assessing this release.

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/WIFI-BRINGUP.md). They are not current installation instructions.
