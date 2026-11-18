> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Wi-Fi — ZX279128S / ZXHN H199A

## Current result — 2026-11-18

The default bank-aware production image booted in bank B with the MT7663
present. The PC's onboard PCI Wi-Fi client associated on channel 149 / VHT80,
WPA2, AP TX power 10 dBm. Ten pings had zero loss. Separate 20-second local
transfers measured 278.7 Mbit/s toward the router and 289.7 Mbit/s from it.
The owner's USB Internet adapter was not used or reconfigured.

Reliability failed: about 33 seconds after the download ended,
`invalid interrupt status: 0xffffffff; device recovery stopped` appeared.
Root-port COMMAND, bus numbers and bridge windows lost their configuration,
initially while glue still reported L0. Later it reported LTSSM state 2;
endpoint config reads were all ones. Root IDs and BAR0/BAR1 stayed unchanged.
AER reported uncorrectable `0x6000` (flow-control protocol, completion timeout),
correctable `0x9100` (replay errors/header-log overflow), and first-error pointer
13 (flow control). This run lacks a complete pre-AP AER baseline, so some
latched errors may predate the transfer.

There was no preceding MCU-timeout/recovery or Ethernet datapath-reset log.
ASPM, L1 substates and mt76 runtime PM were disabled. The same port-0 SerDes
values occurred on a failed boot and this successful association. Vendor
initialization delays were checked against the stock kernel's HZ=100 delay
constants; there is no demonstrated factor-of-two timing error. Holding PERST
through initialization and a 120-second power-off test did not establish a fix.

A subsequent native upgrade booted the same default kernel with port 0 in
LTSSM state `0x2` (not L0), no endpoint, and zero AER uncorrectable/correctable/root
status at the passive baseline. Root command and bridge configuration were
still programmed; a missing endpoint at boot is distinguishable from the
later configuration-loss failure. A private DTB then enabled the stock VID1
port-0 analog branch (this unit reports VID6). The values `0x0046c24a` and
`0x00202d5a` were applied and read back, but the endpoint remained absent at LTSSM `0x2`. This branch is absent from the release DTB and did not establish a fix.

A later private kernel traced both DWC DBI-helper and root PCI configuration
writes, with validated nonzero counts for each path. Both A and B booted it
with the active-bank protections intact. Its read-only board snapshot matched
all six decoded VID6 mux words and GPIO52–55 output directions/levels. A
second private control stopped both LTSSMs, pulsed both existing PERST lines
for 100 ms after clock setup, released them for 200 ms, and retrained before
either PCI host was published. Readbacks succeeded; the missing-link mask
remained `0x1`. It did not recover 5 GHz. The implementation and limitations are
preserved in [tools/diagnostics](../../tools/diagnostics/README.md); neither patch
is applied to the release build.

A final private ordering control held only port 0's LTSSM off during generic
DWC root-complex setup, then used the normal `start_link` callback to enable
it. An initially healthy link would be skipped. The intended down-link path
ran: CTRL was `0x00000008`, DWC port-link control (`0x710`) was `0x00010120`,
and width/speed control (`0x80c`) was `0x0002012c` before enabling. The link
wait still timed out. It added no GPIO pulse or shared-clock/reset operation.
This failed alternative is also preserved as a separate diagnostic patch.

The stock-firmware comparison was independently checked using L0 and BAR
messages, not generic PCI ID text. The healthy stock-A capture preceding B03
reports port 0 L0/Gen1 at count1 and assigns its three endpoint BARs. Later
stock-A and stock-B captures enter the port-0 L0 wait without its success or
BAR messages, while port 1 reaches L0 and gets its BAR. Thus the unit also
reproduces port-0 PCIe initialization failure under stock firmware. That does
not distinguish electrical integrity, retained state or shared initialization
behavior, and does not establish permanent board damage.

These traced boots could not obtain a healthy 5 GHz endpoint, so they did not
capture the earlier runtime failure or prove the absence of CPU writes at
that event. The standard configuration capture includes PM capability writes;
raw LTSSM values are retained without claiming a vendor receiver-detect mapping.
The physical clock, supply and UART back-power/strap conditions remain unmeasured.
The host UART and Internet adapters share an xHCI controller whose USB2 hub
reports no power switching. No USB power or controller reset was attempted.
A physical DC-plus-UART disconnect is the next useful isolation step.

A related [upstream MT7663 report](https://github.com/openwrt/mt76/issues/1154)
describes AP-firmware patch-semaphore failure after warm reboot. Its device
still enumerates, so it is retained-state context rather than an established
explanation for this unit's missing PCIe link.

Client station power save remains a separate untested control: Linux runtime
PM being off does not disable a client's 802.11 PS behavior in the AP firmware.
The next healthy run should record onboard-client PS, disable it before
association, verify it after association/traffic, and compare the same traffic
and idle periods. It was not possible to run that control while the endpoint
was absent. Likewise, a private port-0-only noncoherent-DMA comparison remains
untested; stock explicitly selects coherent DMA for both radios, and initial
link training precedes DMA.

The failure is hardware-observed PCIe/controller configuration loss. The
underlying trigger remains unresolved; a permanent board defect, temperature,
power margin, or a software reset must not be presented as established.
Retain the guard and keep 5 GHz disabled for normal use. The original wireless
configuration was saved and restored byte for byte after this test. The older
sections below are dated investigation records, with hypotheses at that time.

## 2026-11-15: 5 GHz loss reproduced on the production image — it is a port-0 link-down reset

Both bands passed client data tests on `normal-wd` earlier the same day: 5 GHz
284/270 Mbit/s and a 5-minute stress run with 0 errors. On the production NAND
image, a plain 30 s download through NAT, at −36 dBm and VHT80 with the router
transmitting on 5 GHz, lost the MT7663 after about 30 s:
`mt7615e 0000:01:00.0: invalid interrupt status: 0xffffffff; device recovery stopped`.

- **Containment holds.** The 990 guard fail-stopped. There was no panic and
  no reboot, the 2.4 GHz AP kept working, the 5 GHz IRQ went flat, and there
  was no tasklet storm.
- **Fingerprint, captured live:**
  - The endpoint still answered config reads (`14c3:7663`) and the link
    reported 2.5 GT/s ×1.
  - But **both the endpoint and port 0's root port had been reset to
    power-on defaults**: COMMAND 0, endpoint BAR0 unassigned, root-port bus
    numbers and memory window 0.

  So port 0 suffered a **link-down reset**, then retrained. MMIO then hits an
  unprogrammed window, which explains the all-ones. An internal firmware hang
  with the link up cannot produce this, because it would leave config space
  programmed.
- **No in-place recovery.** Removing root port 0 unregisters the driver: one
  `kthread_park` WARNING, then `DMA memory quarantined until reboot; reprobe
  denied`, which is by design. A rescan re-finds the root port, but its config
  writes do not take effect and the endpoint no longer enumerates. Getting
  5 GHz back in place would need a full re-init of port 0 in the host driver.
- **The latch outlives short power cycles and the init sequence.** After
  30 s or 120 s off, the production kernel either does not see the endpoint at
  all, or enumerates it and then cannot reach it. The probe logs `D3cold → D0,
  device inaccessible`, or all-ones DMA indices which the guard quarantines. The
  held-PERST image does enumerate the endpoint after 30 s off, but it never
  probes the radio, so that proves nothing about recovery. The only working
  post-fault probe came after **about 52 min off**. Removing the UART was not
  needed.
- **Not PA current.** With TX power forced to 6 dBm, the same fault came after
  about 100 s of sustained download instead of about 30 s.
- **Thermal is now the leading hypothesis**: the fault comes after sustained
  load, comes later at lower TX power, and the chip recovers only after a long
  cool-down. The next test logs the MT7663 hwmon temperature up to the fault.
- **It can also fault while idle.** On 2026-11-16 the endpoint failed about
  2.5 min after boot, with radio1 disabled and no traffic. Before the guard
  stopped recovery, IRQ 28 stormed (about 250 M interrupts). The kernel's
  spurious-IRQ detector then disabled it (`irq 28: nobody cared`), so boot was
  about 2 min late. The 19:07 fault on the previous image showed the same
  pattern. Disabling the IRQ in the guard's all-ones path would avoid the
  storm.
- **Status:** 5 GHz is functional but **not reliable under sustained TX** on
  this unit. Keep it disabled in production configs until the trigger is fixed.

## Current qualification — 2026-11-11

After the owner disconnected both DC power and UART USB for 30 seconds,
unchanged U enumerated both endpoints. The 5 GHz AP passed exact 1 MiB transfers
in both directions and a 20-second, 100 Mbit/s download. The next upload
stalled. This establishes restored operation after the combined disconnect;
it does not identify which connection or power state caused the earlier fault.

The failure exposed a separate, reproducible recovery defect in the pinned
mt76 source. RX queues held `head=510`, `tail=65535`, `queued=511` for 512-entry
rings; TX cursors were also 65535. A full-width failed index read could be
truncated to 16 bits, then used to refill outside the RX ring. An all-ones TX
completion could also become the signed flush sentinel, and all-ones interrupt
status could invent firmware recovery events. The kernel eventually panicked
in `mt76_dma_rx_reset`. The first MCU timeout was beacon command `0x49ed`.
The initial loss of device access during upload remains unexplained.

`990-dma-invalid-index-fail-stop.patch` rejects full-width invalid indices before
publishing cursors or touching entries. MT7615 rejects inaccessible interrupt
status and stops further recovery/submission after a permanent fault. Final
teardown drains IRQ, tasklet, NAPI and work producers before retiring buffers.
If DMA stop cannot be verified, a private, never-registered resource owner
retains DMA-visible allocations until reboot and denies another probe at that
device identity. Other mt76 drivers retain their existing hardware-stop
responsibility; their final cleanup can still retire valid cached ownership
after the shared failure latch is set.

The patch has host C fault-injection coverage and an ARM build. It has **not
been loaded or qualified on hardware**. All five matching modules must be
replaced together (`mt76`, `mt76-connac-lib`, `mt7615-common`, `mt7615e`,
`mt7603e`), because common structure layouts changed. Do not load only the leaf
driver over the old NAND root's modules.

Candidate W adds an opt-in `pcie_zx279128.hold_perst=1` experiment: hold both
endpoint reset pins low through shared setup, stop LTSSM while held, allow a
100 ms settling interval, then release and train. The interval is a conservative
test allowance, not measured reference-clock lock. The default path is
unchanged. W is read-only, blacklists both radios and sets `panic=0`; it is
packed but not hardware-qualified. Two boot attempts could not establish the
bootloader prompt because UART output was garbled or missing. The controller
powered off on failure; neither attempt loaded W.

Both radios carried verified traffic on M. Qualification must still be repeated
on the final native-storage image and normal OpenWrt userspace; historical
results below are not substitutes for those checks.

Later N/O/Q cold boots fail port0 link training, and an unchanged M control now
reproduces that failure before NAND initialization. O prepares both controllers
before either bus scan; Q additionally confirms each PERST low/high edge and
completes the timed CRM writes with readbacks. Q verifies both reset pins but
still reports port0 LTSSM state 3; a longer power-off interval did not help.
Port1 reaches L0. The diagnostic common-preparation gate publishes neither bus
when either final link check fails. These changes have not resolved 5 GHz
reliability; native SPI is not established as the cause.

S separates completion of the shared reset sequence from each port's link
state, so the healthy 2.4 GHz endpoint can enumerate while 5 GHz remains absent.
Its MT7603 firmware and WPA2 AP initialize successfully. The BCM43569 client
still times out without a radio reset; an OFDM-only rates control also fails
to authenticate, and the original AP rates were restored afterward.

The contained stock-kernel R reference reproduces the same split twice: the
vendor port0 routine does not report L0, while port1 reports Gen1 and receives
its BAR. `tools/stock-pci-image.py` accepts only the corrected identified stock
image and disables NAND/watchdog registration plus automatic panic reboot in
the RAM copy. It preserves every other decompressed byte and the appended DTB.
The controller supplies explicit 128 MiB/read-only arguments, verifies the
known U-Boot trailer, and powers off after the intended root-mount failure.
The first capture's overly strict command-line check rejected that trailer;
the repeat passed the corrected check. Neither capture initialized NAND, and
a subsequent full corrected data+OOB backup matches the pre-test hash exactly.

Disabling the watchdog did not omit a required shared-clock transition: SPL
already writes TOPCRM `94000004=1fb`, including the bits its watchdog probe
would OR with `18`. Q reads back the same value. The watchdog path has no PCIe
PLL/reset/pinmux writes. GPIO52/54 low and PERST53/55 high also match the verified
stock and U-Boot tables. The failure therefore also occurs with the unit's own
vendor PCIe initialization; this guarded reference does not prove a hardware
fault or substitute for a complete unmodified vendor boot.

Candidate M starts a WPA2 MT7603 AP with the correct factory MAC and recovered
base calibration merged with this unit's OTP. The owner's Android phone joins,
receives DHCP and passes exact 1 MiB uploads and downloads under normal SMP
scheduling and a forced-CPU1 control. Both modes passed roughly 75 MB downloads
at 10 Mbit/s. A two-minute CPU1 download received 347,865,088 bytes at
23.19 Mbit/s while CPU0 performed 512 fresh program loads and a full verified
NAND rootfs read. Radio reset counters and NAND transport errors remained zero.
M also passes a repeated cold boot and another 75 MB 2G download. Its 5 GHz
device retains stable PCI configuration, initializes with coherent DMA and
starts a VHT80 AP on channel 36. The phone passes exact 1 MiB transfers and
60-second uploads/downloads at approximately 100 Mbit/s (750 MB each).

With the PC's USB client on 5 GHz and the phone on 2.4 GHz, simultaneous
120-second downloads receive 1,499,987,968 bytes at 99.998 Mbit/s and
149,946,368 bytes at 9.996 Mbit/s respectively. Kernel interface error/drop
counters remain zero. More dual-radio cold boots, peak throughput and a long
load test remain to be established.

The BCM43569 USB client still fails to authenticate on 2.4 GHz, while it
associates and carries data on 5 GHz. A separate host USB re-enumeration during
setup invalidated an earlier client-data attempt; it was corrected before the
successful concurrent test. This client/band compatibility issue remains open.

I includes the stock I/O coherency sequence and coherent PCI DMA declarations;
all five setup readbacks match and runtime MT7603 metadata reports coherent
DMA. See [platform evidence](../BRINGUP.md#2026-11-10-early-io-coherency-initialization).
An earlier I run overlapped a classifier-register read that never returned;
that run cannot distinguish a transfer failure from a diagnostic bus stall.
J restores the verified stock PL310 policy and Ethernet RX correctness fixes,
but still hangs during unrestricted/CPU1 downloads. L fixes missing NAND
PAGE13 preparation. M additionally selects the standard coherent PL310 mode.
Repeating L with the same kernel and only that DT property disabled reproduced
the CPU1 hang after 808,152 bytes. See the
[cache/PCI investigation](../BRINGUP.md#2026-11-11-coherent-pl310-mode-passes-the-cpu1-control)
for the isolated comparison and vendor serialization evidence.

**The previous empty-eFuse / generic-calibration conclusion is withdrawn.**
An actual read of MT7603 `eeprom` and `otp` returned identical 1,024-byte buffers,
SHA256 `3999b4ed085f4dd9acb957442d2d55e8ad4eb264078d4a0587f4bdfbd7314606`.
They contain the eight factory trim bytes expected by mt76's calibration-free
merge path. The chip ID and base power/rate tables are erased. This is a sparse
OTP fragment, not a complete EEPROM. The driver currently copies it wholesale
when no valid base is supplied. Erased rate bytes are interpreted as positive
power offsets, so the displayed regulatory-limit TX power is not proof of
correct calibration. The correct base has since been recovered from this unit's
vendor filesystem; the RAM experiment below verifies its native OTP merge.

Exact packaged source is OpenWrt mt76 `eb567bc7f9b692bbf1ddfe31dd740861c58ec85b`,
with mac80211 backports based on 6.12.96. See its
[EEPROM handling](https://raw.githubusercontent.com/openwrt/mt76/eb567bc7f9b692bbf1ddfe31dd740861c58ec85b/mt7603/eeprom.c)
and [power setup](https://raw.githubusercontent.com/openwrt/mt76/eb567bc7f9b692bbf1ddfe31dd740861c58ec85b/mt7603/init.c).

The 5 GHz endpoint was absent on B/C RAM boots. Port0 sometimes reports
initial Gen1 link-up, then PCI core lifts that restriction and no endpoint is
found; another boot fails initial training. Older successful boots also contain
the speed-promotion message, so it is not a complete causal explanation.
`max-link-speed = <1>` now preserves the intended limit through DesignWare
setup and generic retraining. Later boots enumerate the endpoint, but stable
PCI access and driver startup still need qualification. Do not claim 5 GHz is working merely
because `modprobe mt7615e` returns zero: it can load with no matching PCI device.

### Original base recovered and merged

The corrected stock kernel and filesystem pass their container/gzip CRCs.
Its `part_read` decrypts 2048-byte pages with AES-128 ECB; `combine_token`
constructs the key from kernel constants. The offline extractor derives that
key from a hash-identified kernel, validates the whole plaintext digest and
every JFFS2 node/name/data CRC, then extracts the original files. It contains no
vendor firmware or embedded key:

```sh
python3 tools/extract-stock-calibration.py \
  /private/stock-kernel-b-ecc.bin /private/stock-rootfs-b-ecc.bin \
  /private/h199a-original-calibration
```

This supports the identified July 2021 firmware only and requires Python 3 and
OpenSSL libcrypto. The output directory must be new; `verification.json` marks
a completed extraction. Keep extracted vendor files with private backups.

The selected 2G base is the original
`/etc/Wireless/MT7603e/MT7603E_EEPROM.bin`, 512 bytes, SHA256
`c2c0f5acfc78f63edb6b9b2b1dea95f03274b4b489769344be9380d0cde88cc5`.
The vendor copies `RT2860AP.dat` into `/var/tmp`; its `E2pAccessMode=2` selects
flash access. Since this unit's first 512 bytes of `wifi` are erased, its driver
loads this filesystem file. A different compiled `MT7603_E2PImage` is used only
if that file cannot be opened. Do not conflate those two bases.

Candidate E supplies the exact 512 bytes through `mediatek,eeprom-data` and sets
`mediatek,eeprom-merge-otp`. The exact packaged mt76 implementation accepts that
short property in its zero-initialized 1024-byte buffer. Its live EEPROM SHA256
is `81fbf20df994fab23218933a381789db67528b4ef92188acc2d3a3f0b3bffe6c`, exactly
matching the original base with the eight own-unit trims merged. The reported
AP power changed from 30 to 24 dBm; firmware initialization and AP start pass.
This does not yet qualify calibrated RF performance or general image delivery.

### Owner-supplied calibration in the build

After extracting the supported own-stock firmware above, pass its original
512-byte `MT7603E_EEPROM.bin` to the normal build:

```sh
H199A_HEADER=/private/header-template.bin \
H199A_MT7603_EEPROM=/private/h199a-original-calibration/MT7603E_EEPROM.bin \
./build.sh
```

Install the host `device-tree-compiler` package, which supplies `fdtget` (and
`dtc`/`fdtput` used by the tests). The build checks for `fdtget` before preparation.
`tools/h199a-calibration.py` validates the length, chip ID and qualified base
hash before build preparation. It generates an include and binary only in the
ignored OpenWrt build tree, attached to the public `wifi2g` label. The device
still supplies its own trim bytes through `mediatek,eeprom-merge-otp`, and its
MAC through the existing tag NVMEM cell. No userspace OTP merge or manual
1024-byte padding is performed. Normal builds reject missing calibration;
diagnostic builds may omit it for non-radio work. Switching inputs/profiles
removes stale generated calibration files.

The final build checks the image DTB's exact bytes and merge property, confirms
that the sysupgrade kernel contains that DTB with valid wrapper CRCs, and
writes a companion `*-calibration.json` containing EEPROM, DTB and image hashes.
The source recipe contains no EEPROM binary; treat the resulting image as an
owner-supplied build. A generic binary that loads calibration after installation
would require additional loader support. Both DT properties are already
documented in the [upstream Linux binding](https://raw.githubusercontent.com/torvalds/linux/v6.6/Documentation/devicetree/bindings/net/wireless/mediatek,mt76.yaml).

The BCM43569 USB client still times out. Hardware MAC/BSSID readbacks match
the AP, and raw-monitor address filters are clear. A bounded capture counted
1778 received frames with RX signal metadata, including other beacons/probe
responses, but no authentication frame for this AP or test client. Saved own-AP
beacons were local TX-status copies, not over-air RX evidence. A separate BRAVO
baseline stopped waiting for an unavailable saved credential and is invalid as
an adapter test. Independent-client validation remains useful.

The owner's Android phone subsequently joined candidate F, completed WPA2,
received a DHCP lease and opened the local test page. This establishes an
independent client and application-data pass with the corrected base. The phone
is now attached through ADB for automated testing. On F, a larger 2 MiB HTTP download
stopped after 369,067 body bytes; wired/WiFi ping and a fresh UART command then
all failed while the UART logger remained healthy. Bulk-transfer reliability
is therefore still a blocking requirement, despite the successful small page.

### PCIe timing and failed probe evidence

Candidate D's initial scan reported BAR0 update errors before port1 initialization;
loading the 5G driver then panicked. Actual module disassembly and the stack
prove RX queue index 65535, propagated unchecked from the hardware index into
an out-of-bounds queue entry and then a zero DMA address. The secondary CPU's
all-ones MMIO read supports lost access; it was not the initial exception.

The verified vendor kernel waits 50 ms after port0's configuration enable,
clock bits 15/13/14, and reset assertion. Four of those waits were only 1 ms in
this driver. Candidate F restores them and requests retraining with a 16-bit
Link Control write after the existing PERST pulse. This is a hybrid sequence:
the vendor releases PERST earlier and initializes both hosts before scanning.

F discovered and assigned BAR0/2/4 without errors on its first boot. Live chip
ID/revision and queue-index reads passed with MEM enabled and bus mastering
off. The subsequent module probe nevertheless failed IRQ parsing with PCI
configuration status 134. Later glue snapshots moved from L0 to recovery states
0x10/0x0d; wired liveness remained 60/60. F is not a completed PCIe fix. The
actual port1 reset/configuration masks also differ from the earlier inferred
ones. Candidate G applies the verified port1 sequence, including the final
shared reset-register write of `0x3f`. Its readback is `0x1b`; the individual
bits' behavior is not established, so that readback alone proves neither a
failed write nor a correct hardware effect. G/H still show unstable port0
configuration access. The vendor prepares both hosts before scanning either;
the present per-host sequence has not yet reproduced that ordering. Do not
bypass link checks to hide failure. CRM2 offset `0x0c` is a pinmux word; the
affected pins and any PHY relationship remain unproven.

## Historical tests

Status: **the 5 GHz access point works** - a client associates, gets a DHCP lease
from the device, and passes traffic, verified on the CURRENT shipped image
(round 239).
History and withdrawn hypotheses: [`WIFI-JOURNAL.md`](../WIFI-JOURNAL.md).

## ★ The AP is the device's MANAGEMENT path — LuCI and SSH work over it (2026-09-06)

Inbound TCP does not terminate over Ethernet, and that has been recorded for
most of this project's life as "no SSH, no LuCI, no `opkg`". It is a **wired**
defect. mt76 receives by its own PCIe DMA on its own NAPI, so the NPP classifier
that eats wired SYNs is not in the Wi-Fi path at all.

Measured from a real 5 GHz client on the shipped image:

```
wlan0 inet 192.168.1.146/24               <- lease from the device's dnsmasq
ping 192.168.1.1       : 4/4, 0% loss, avg 4.8 ms
nc -vz 192.168.1.1 22  : Connection to 192.168.1.1 22 port [tcp/ssh] succeeded!
curl http://192.168.1.1/ : HTTP=200 in 0.77 s, body is LuCI's HTML
```

with the wired host, in the same session, timing out on both ports. `luci` is
therefore now in `seed.config`: the web UI has a transport that works.

**Reliability caveat, and it is a large one.** Three trials were run; only the
first completed. In the other two the client associated (and in one, took its
DHCP lease) and then the whole device wedged — wired path to 100% loss and the
serial console accepting keystrokes but never executing them, recoverable only
by a power cycle. Treat "LuCI over Wi-Fi" as demonstrated, not as dependable.

## The firmware-load hang: what is measured, and what is NOT fixed

Every trial below is its own cold boot, because a hang is only recoverable by a
power cycle.

| arm | trials | system hangs |
|---|---|---|
| `mt7615e` autoloaded at boot by kmodloader | 6 | **4** (three consecutive) |
| `modprobe` typed at a shell, ~3–4 min after power-on | 6 | **0** |
| `modprobe` **+ `wifi up`** typed at a shell, same timing | 3 | **0** |
| **`/etc/init.d/zx-wifi-late`, 20 s after procd starts** | **4** | **2** |

✗ **RETRACTED, within the same session: "deferring the load avoids the hang."**
That is what the first three rows looked like, and it is what this section
originally claimed. The fourth row is the test of the shipped fix, and it fails:
loading the module from an init script 20 s into boot hangs about as often as
letting kmodloader do it.

So the clean arms and the failing arm differ by **more than "boot versus
runtime"**. The clean ones were typed at an interactive shell on a quiescent
system three or four minutes after power-on; the failing one runs 20 s in, while
the rest of boot is still going. Time-since-boot, or concurrent boot activity, is
the variable — and "boot-time versus run-time" was too coarse a way to describe
it. A 150 s delay was tried and produced no hang in 2 boots, which is **two data
points and therefore nothing**; on this hardware one measurement is zero
measurements.

**What IS supported:** the mechanism is not a large squashfs read on the ECC-less
NAND. One of the clean arms pre-read the firmware file into page cache before
loading and the other did not; both were clean, so the preload changed nothing.

**What ships, and why it is still there.** `/etc/modules.d/mt7615e` **and**
`/etc/modules.d/mt7603` are emptied at build time through `$(TOPDIR)/files` so
kmodloader does not load either driver, and `/etc/init.d/zx-wifi-late` loads them
afterwards.

> `mt7603e` was added on 2026-09-07. Until then only the 5 GHz radio was
> deferred and the 2.4 GHz one still loaded from kmodloader at ~t+112 s, which
> means the "deferred load" arms measured to date were never actually radio-free
> before the deferral fired — and the sweep's "each radio alone" arm could not
> have worked at all, because one of the two radios was going to load whatever
> the arm said. Keep expectations correct: this
is **not** a fix. Its one demonstrated property is that the hang, when it
happens, now happens *after* userspace is up rather than before it, so the device
has usually reached a shell and a working wired path first. Boots still hang.

**If you are continuing this:** the next real experiment is a proper sweep of the
delay (30 / 60 / 120 / 240 s), alternating arms, at least five cold boots per
arm, scored from the UART log rather than from a console probe — the console
probe used here was itself unreliable and scored a healthy device as failing more
than once.

## ⚠️ How bad the boot-time hang was, on this image

`README.md` records 43 of 194 firmware loads (22.2%) failing to reach
`N9 Firmware Version`. On 2026-09-06, on the freshly flashed image, six
consecutive cold boots with `mt7615e` autoloading gave **four hangs**, including
three in a row. Every one stopped at exactly the same line:

```
mt7615e 0000:01:00.0: HW/SW Version: 0x65322d31, Build Time: 2009041715da1a1
```

and produced no further console output at all — not the next driver line, not
procd, not the shell. It is a whole-system hang, not a Wi-Fi failure.

That is a small sample and it is not being offered as a new rate; the point is
narrower and practical: **on this image the hang is frequent enough that it, not
the classifier, is what stands between you and a usable device.** The same
signature was also produced by a *runtime* `modprobe mt7615e` + `wifi up`, which
means it can be studied without waiting for a boot to fail.

## ★★★ 2.4 GHz WORKS (2026-09-06)

Verified end to end on hardware:

```
phy0-ap0  ESSID: "H199A-24G"
          Mode: Master   Channel: 6 (2.437 GHz)   HT Mode: HT20
          Tx-Power: 30 dBm
device: Station 14:cc:20:23:9a:f1 (on phy0-ap0)   rx packets: 64
client: inet 192.168.1.101/24            <- lease from the device's dnsmasq
        ping 192.168.1.1 -> 5/5, 0% loss, avg 0.79 ms
        curl http://192.168.1.1/ -> HTTP 200, LuCI's HTML
```

`/sys/class/ieee80211/phy0/device` -> `0001:01:00.0`, i.e. the MT7603E on PCIe
port 1, and `wifi config` auto-detects it as `band='2g'`.

### What was actually wrong: our own interrupt map

Three things had to be fixed, and only the first was ever suspected:

1. **A missing clock triple.** Port 0 enables three contiguous bits in
   `CRM0[0x08]` (15, 13, 14, staged); port 1 needs the mirror triple 25/26/27
   and the driver set only bit 27. Without it the first DBI read raised an
   imprecise external abort that wedged CPU 0 dead. This is what made the port
   train at all.
2. **PERST# was pulsed on both ports.** Harmless while port 1 was disabled;
   with both probing it would reset the MT7613BE off the bus after it had
   trained. Now per-port.
3. ★ **`pcie1`'s `interrupt-map` was a verbatim copy of `pcie0`'s**, so both
   endpoints were assigned Linux IRQ 27 (GIC hwirq 95 = SPI 63) and the
   MT7603E's handler sat on port 0's wire. Its MCU download then timed out at
   `-110` every time.

The stock DTS lists four interrupts for its single PCIe node — `63, 78, 59, 74`
— and this port had read them as INTA-D of one port. They are not. Sorted they
are 59, 63, 74, 78, and **`63->78` and `59->74` are both +15**: two ports x two
lines, interleaved exactly in the order the stock DTS lists them, i.e.
port0-A, port1-A, port0-B, port1-B.

**How that was measured rather than guessed.** For a level-sensitive SPI the
GIC's pending bit follows the input line, so with the MT7603E asserting and
nobody servicing it, the line had to be sitting high. Reading `GICD_ISPENDR`
(`0x00801200`+) on a bring-up build:

```
word 2 (IDs 64-95)  = 0x00500000   -> SPIs 52, 54 (other devices)
                                      SPI 63 NOT pending - mt7615e services it
word 3 (IDs 96-127) = 0x00004000   -> bit 14 = ID 110 = SPI 78, pending
```

Exactly one unserviced line, and it was SPI 78. After remapping, the proof:

```
27:  39  0  GIC-0 110 Level  mt7603e      <- GIC 110 = SPI 78, and counting
```

### ★ Both radios now carry their FACTORY MACs (2026-09-06)

The MT7603E used to report `Invalid MAC address, using random address` and take
a different address every boot. Fixed, and the assignment is the vendor's own.

**Where the radio MACs live, from the stock firmware's own web UI** (captured in
`research/webui-capture/`, so this is the vendor naming them, not a guess):

```
SSID1 (2.4GHz)  Nome SSID Tp-Link 2G   Endereco MAC 02:00:00:00:00:03
SSID5 (5GHz)    Nome SSID Tp-Link      Endereco MAC 02:00:00:00:00:04
```

Those are `tag` records **0 and 1** — the two the Ethernet ports had been
claiming. The vendor derives its extra BSSIDs from them by setting the
locally-administered bit and putting the SSID index in byte 3's high nibble:
`06:20:84:1f:87:b3`, `2f`, `3f` for SSID2/3/4, and the same on `...b4` for
SSID6/7/8.

So the split is now:

| consumer | address | source |
|---|---|---|
| 2.4 GHz radio (`phy0`, `0001:01:00.0`) | `02:00:00:00:00:03` | tag record 0, via DT nvmem |
| 5 GHz radio (`phy1`, `0000:01:00.0`) | `02:00:00:00:00:04` | tag record 1, via DT nvmem |
| `eth0` | `02:00:00:00:00:05` | tag record 2, via DT nvmem |
| `eth1`/`eth2`/`eth3` | `06:20:84:{1,2,3}f:87:b5` | derived by the driver |

The Ethernet derivation copies the vendor's own scheme rather than incrementing
the last octet, which would walk into `...b7` — an address belonging to somebody
else's unit. The locally-administered range does not.

Verified on the flashed image, both sides:

```
device: iwinfo phy0-ap0 -> Access Point: 02:00:00:00:00:03   Channel: 6
        iw dev phy0-ap0 station dump -> Station 14:cc:20:23:9a:f1
client: nmcli -> * H199A-24G  02:00:00:00:00:03  chan 6
        192.168.1.101/24, ping 192.168.1.1 -> 4/4, 0% loss, avg 0.78 ms
        dmesg | grep -c "random address" -> 0
```

Note the 5 GHz radio's calibration blob contains `00:0c:43:26:60:00`, a MediaTek
default identical on every unit; the DT nvmem cell overrides it, so that radio
gets its real address too.

### Still imperfect

* TX power reads 30 dBm on 2.4 GHz, which is the regulatory default rather than
  a calibrated value — with no EEPROM and an empty eFuse, mt76 gives a
  functional radio with undefined calibration.

## Hardware

- The module is an **MT7613BE** on PCIe port 0 — **5 GHz-only silicon**.
- Binds `mt7615e` as `0000:01:00.0 [14c3:7663]`, firmware
  `mt7663pr2h_rebb.bin`.
- Calibration comes from the `wifi` MTD partition at `+0x20000`, wired in the
  device tree by phandle (`mediatek,mtd-eeprom`), giving 24 dBm. Without it the
  radio comes up at reduced power with a random MAC.
- The SoC PCIe controller is Synopsys DesignWare, **pre-v4.70a** (legacy iATU
  viewport at DBI+0x900); driver `drivers/pci/controller/dwc/pcie-zx279128.c`.

## What is verified on the current image

A dual-core boot of the current build, checked directly:

```
phy0-ap0  ESSID: "H199A-TEST"
          Mode: Master  Channel: 36 (5.180 GHz)  HT Mode: VHT80
          Tx-Power: 24 dBm   Noise: -92 dBm
br-lan: port 2(phy0-ap0) entered forwarding state
```

So: the driver binds, the radio comes up in Master mode on a 5 GHz channel at
VHT80, calibration loads from flash, and the interface is a member of `br-lan`
(though unicast forwarding across the Wi-Fi/wired boundary does NOT work - see the
round-240 note below). Enabling SMP did not affect any of it.

Re-confirmed round 239 on the shipped flash image: `phy0-ap0` present, type AP,
SSID `H199A-TEST`, `channel 36 (5180 MHz) width 80 MHz`, `txpower 24.00 dBm` -
i.e. the AP is up and the radio is transmitting at full calibrated power on the
current artifact, not just an old build.

## Association, DHCP and traffic - VERIFIED on the current image (round 239)

A real 5 GHz client (`tiny`, an RPi) associated to `H199A-TEST` on the shipped
flash image and the full path worked:

```
wlan0  ESSID:"H199A-TEST"  state: 100 (connected)
DHCP:  inet 192.168.1.146/24        <- lease served by the device's dnsmasq
ping 192.168.1.1: 5 packets, 0% loss, avg 3.7 ms
```

So on the current artifact the device is a **functional 5 GHz access point**: a
client associates, the device's DHCP server issues a lease, and bidirectional
traffic flows. This was previously verified only on an older build; it now holds
on the image `build.sh` produces.

### Client forwarding to the wired LAN is too lossy to use (rounds 240 + 244)

A client reaches the DEVICE, but not hosts on the wired LAN through it:

```
tiny (Wi-Fi 192.168.1.146) -> ZTE 192.168.1.1  : 0% loss           (client to device: works)
tiny (Wi-Fi 192.168.1.146) -> host 192.168.1.100: 87.5-100% loss   (Wi-Fi -> wired LAN: unusable)
```

Round 240 saw 100% loss and read it as "forwarding disabled". Round 244 probed
deeper with the device's own counters: `phy0-ap0` RX climbed to 830 and `eth0` TX
incremented by ~40 during the test, and the client saw 87.5% loss (1 of 8 pings).

**The mechanism inferred from that - "the bridge forwards but the wired TX path
drops ~90%" - is RETRACTED.** The round-246 adversarial audit (Claim B, below)
ran the missing controls: 8 host->device pings alone produce +13 `eth0` TX, so
the "+40" is not attributable to forwarding; and the wired path loses **15-35%
for the device's OWN traffic** with no client associated. That is the noise floor
the 87.5% was measured against, from an 8-ping sample with no baseline.

What stands: forwarding is **unusable** (87.5-100% client-visible loss,
reproduced twice). Where the loss occurs is NOT established. (Round 247 attempted
an independent control arm - associate but stay idle, measure Round 247 attempted the control arm - associate but stay idle, measure
the TX delta - but the client's association to this AP is FLAKY, ~50% success
across the session (NetworkManager "802.1X supplicant took too long"), and it
failed on every control-arm attempt, so the isolation stays undone. The
association flakiness is itself a real quality signal about this AP.)

The mechanism matters for anyone continuing: it is the wired TX path dropping
frames, not a bridge/config problem - the same poor wired-datapath quality as the
RX delivery band (~50%) and the wedge, worse for TX, with the known TX buffer
leak (`zx_bm_alloc()`'s result discarded for a dedicated index) sitting on it.

**Net:** a working AP for client-to-device traffic (DHCP, DNS, management), but
forwarding to the wired LAN is unusable (87.5-100% client-visible loss). The round-223 argument that
the wedge does not bound the AP use case holds only for client-to-device
traffic.

### Test method (safe, self-restoring)

`tiny`'s only uplink is `wlan0` (its SSH path), so the test ran as a detached
script with a `trap restore EXIT` that returns `wlan0` to its normal network even
if SSH drops during association. The AP is open (`encryption='none'`), so no key
was needed. BRAVO (tiny's normal network) was restored automatically and SSH
recovered.

## What does not work

- ~~**2.4 GHz is absent.**~~ **PCIe port 1 now trains and the MT7603E
  enumerates** (2026-09-06) — see the section above. What remains open is
  whether it comes all the way up as a usable AP: its eFuse carries no MAC
  ("Invalid MAC address, using random address") and there is no second
  calibration blob in the `wifi` partition.
- **Sustained goodput through the AP has not been measured.** The frequently
  quoted 433.3 Mbit/s is a negotiated **link rate** from `station dump`, not
  goodput. A 30 Mbit UDP attempt tiny->host was tried (round 240) and it **wedged
  the wired path** (100% loss until a power cycle) before producing a number, so
  the forwarding path cannot sustain that rate - see the round-240 note above.

- **Why client-to-device traffic works while forwarding does not (the
  architecture behind the round-239/240 results).** Verified topology from the
  device's own boot log: `br-lan` bridges **`eth0`** (the wedging `zx279128-eth`
  driver) and **`phy0-ap0`** (mt76), holds 192.168.1.1/24, and runs dnsmasq.

  The wedge budget is structurally wired-side. `zx_eth_rx_timer` fires an
  hrtimer, `napi_schedule`s the driver's own NAPI, and its poll drains the
  **wired MAC's descriptor ring**. A Wi-Fi frame never enters that ring - it
  arrives by mt76's PCIe DMA on a separate NAPI - so a client talking TO the
  device (DHCP/DNS/ping the gateway) does not touch the wired RX budget. That is
  why round 239's association + client-to-device test passed cleanly.

  But **forwarding a client onto the wired LAN needs `eth0` TX**, and forwarding
  is unreliable in practice (87.5-100% client-visible loss). The round-244
  attempt to pin this on "the wired TX path drops ~90% of forwarded frames" is
  **retracted - it had no control** (see the round-246 audit below). Net: the
  wired wedge does not bound *client-to-device* traffic, but *forwarding* is
  unusable in practice - by a mechanism that is not established.

## 2026-09-08: the 2.4 GHz autoload override used the wrong filename

The running device contained `/etc/modules.d/mt7603` with `mt7603e` in it.
The recipe instead emptied `/etc/modules.d/mt7603e`, which is not the file
installed by `kmod-mt7603`. Consequently the 2.4 GHz driver still loaded during
kmodloader, even with `zx-wifi-late` disabled and its module list set to `none`.
The override now uses the package filename, `mt7603`, and CI checks that both
radio autoload overrides exist and are empty.

A cold boot after emptying the correct file reached userspace without either
radio loading. That boot is not a delay-sweep result: the staged init script
was not executable, so its deferred load never ran. The deployment mode was
corrected before retrying. Older claims that both radios were deferred need
their boot logs checked for early `mt7603e` initialization.

The bench scorer now requires the requested ARM and DONE lines, plus a shell
response that cannot be satisfied by the UART's command echo. Missing or
mismatched load markers are INCONCLUSIVE. The arm setter checks both the
delay and module list and refuses a disabled/non-executable service. A failed
modprobe now emits FAILED and cannot emit DONE.

With the corrected autoload files, the first alternating delay cycle reproduced
the mt7615 HW/SW-line hang at **30, 60, 120 and 240 seconds**. Each hung trial
had no shell response or wired ping response after its full observation window.
The 60-second boot also reported SquashFS read errors before WiFi and is
confounded. An earlier corrected 30-second boot passed, so this remains
intermittent. No tested delay eliminated the hang; failed arms were stopped
after reproduction rather than repeated to estimate a failure rate.

Radio isolation: a 2.4 GHz-only boot reached its AP and answered the generated
shell probe. The scorer initially recorded NOBOOT because the response arrived
after its four-second window, during ash/profile startup. That row is retracted
as a device failure; the UART contains `TRIAL431130X1ALIVE`. The probe now polls
for up to 30 seconds and has a delayed-response regression case. Loading
`mt7603e` before `mt7615e` still reproduced the 5 GHz firmware hang.
The 5 GHz-only arm (`30:mt7615e`) also hung at its HW/SW line with both shell
and wired ping down after the longer reply window. Neither the tested delays
nor presence/load order of the second radio eliminates the failure.

## Bringing it up

The radio ships **disabled**; a fresh flash comes up with no wireless config.

```sh
uci set wireless.radio0.disabled=0
uci set wireless.radio0.country=<ISO code>
uci set wireless.default_radio0.ssid=<ssid>
uci set wireless.default_radio0.encryption=psk2
uci set wireless.default_radio0.key=<passphrase>
uci commit wireless && wifi up
```

## How to verify

```sh
ls /sys/class/ieee80211/        # phy0
iwinfo                          # Master, VHT80, 24 dBm
iw dev phy0-ap0 station dump    # after a client associates
```

## Open questions

- PCIe port 1 (2.4 GHz). Port-0 bring-up is understood and works; port 1's glue
  base is unknown — a read probe proved `0x09600000` does not decode, and the
  vendor resource table does not name it.

## Round-246 adversarial audit of the round-239/244 claims

Both claims were re-tested against controls. One is now proven with independent
device-side evidence; the other's *mechanism* is retracted.

### Claim A - "the AP works: client associates, gets a lease, passes traffic" - **PROVEN**

Re-run capturing BOTH sides simultaneously, plus a null control:

```
NULL CONTROL  tiny on its normal network (BRAVO): ping 192.168.1.1 -> 100% loss
              tiny has NO other route to 192.168.1.0/24; its wired eth0 to the
              ZTE is NO-CARRIER/DOWN. So reaching .1 is only possible via the AP.

DEVICE SIDE   iw dev phy0-ap0 station dump -> Station e4:5f:01:04:98:b0
              /tmp/dhcp.leases -> e4:5f:01:04:98:b0 192.168.1.146 tiny
              phy0-ap0 BSSID        -> 00:0c:43:26:60:00

CLIENT SIDE   wlan0 MAC             -> e4:5f:01:04:98:b0     (matches station)
              iwgetid --ap          -> 00:0C:43:26:60:00     (matches BSSID)
              NetworkManager        -> "new lease, address=192.168.1.146"
              ping 192.168.1.1      -> 5/5, 0% loss
```

The BSSID matches the device's own AP, the associated station MAC matches the
client, and the lease appears in **the device's own dnsmasq lease file** with the
client's MAC and hostname. This closes every false-positive route considered:
not a stale/self-assigned address, not another DHCP server, not another AP, and
not a different network path.

### Claim B - "the bridge forwards but wired TX drops ~90%" - **mechanism UNSUPPORTED**

The round-244 reasoning was: `eth0` TX incremented ~40 during the forwarding
test, therefore frames reached the wired transmitter, therefore the ~90%
client-visible loss is the TX path dropping them. **That test had no control**,
and two measurements undermine it:

```
CONTROL 1  With NO client associated, 8 host->device pings alone produced
           +13 eth0 TX. Device-originated traffic (ARP, ICMP replies, dnsmasq)
           uses the same counter, so "+40" is not attributable to forwarding.

CONTROL 2  Device-own wired loss, no client and no forwarding at all, five
           consecutive 20-ping runs: 15%, 15%, 25%, 35%, 15%
           (and 5%, 5%, 30% in earlier runs)
```

So the wired path loses **15-35% for the device's own traffic**, highly variable
run to run. That is the noise floor the "~90% forwarding loss" was measured
against, with no baseline taken at the time and a sample of 8 pings.

What remains solid: **forwarding is unreliable enough to be unusable**
(87.5-100% client-visible loss, reproduced twice). What is NOT established: that
the loss occurs specifically in the wired TX path, or that it is ~90% rather than
the compounding of an already-lossy wired path with something else. Anyone
continuing this should measure `eth0` TX *errors* and the host's received count
directly, with a no-client baseline in the same session.

## ★ 2026-09-07 — 2.4 GHz TX power is not a port defect; there is nothing to calibrate against

`README.md` lists "2.4 GHz TX power is a regulatory default, not calibrated" as
an open item. Re-examined, and it should be reclassified: **this is a property
of the unit, not a defect in the port.**

The chain of facts:

* A scan of the whole 1 MiB `wifi` partition found exactly **one** non-blank
  4 KiB chunk, at `+0x20000`, and it is the MT7663 (5 GHz) blob — chip id
  `0x7663` plus a MAC. There is no second blob anywhere in flash.
* The MT7603E's eFuse is empty.
* Consequently `pcie1` in our DTS carries **no** `mediatek,mtd-eeprom` phandle,
  because there is nothing to point it at.

What mt76 then does, from its own source (`mt7603/eeprom.c`): `mt7603_eeprom_init()`
loads what it can, and `mt7603_apply_cal_free_data()` is gated behind
`mt7603_has_cal_free_data()`, which bails immediately if
`MT_EE_TEMP_SENSOR_CAL`, the 2G TX power start words, `MT_EE_CP_FT_VERSION` or
the crystal fields are zero. An empty eFuse fails that test on the first check,
so **no calibration is applied and the driver runs on a zeroed EEPROM**, falling
back to regulatory limits. That is exactly the 30 dBm regulatory default we see.

**The vendor firmware faces the identical situation** — same empty eFuse, same
absent blob. There is no per-unit 2.4 GHz calibration on this device for anyone
to load, ours or theirs.

### Why "source a generic blob from another unit" is the wrong fix

It was considered. It is worse than the default: another unit's calibration
describes *that* unit's PA and antenna path, so loading it would replace a
known-conservative regulatory number with a confidently wrong one, and the error
would be silent. mt76's zeroed-EEPROM path already *is* the generic default.

**Resolution: document it as a permanent characteristic and close the item.**
The radio is functional and associates, passes traffic and serves LuCI at 0%
loss. What is unavailable is a per-unit power table, and it is unavailable
because the vendor never wrote one.

Two things that would change this conclusion, neither cheap: a spectrum analyser
and a hand-built table valid for this unit only, or discovering that the vendor
stores 2.4 GHz calibration somewhere outside the `wifi` partition (the whole
128 MiB dump has been scanned once; a second look would need a different search
than "find a 4 KiB non-blank chunk").

## ★ 2026-09-07 — the firmware-load hang reproduced and captured, and two harness traps that invalidate naive sweeps

The delay sweep this file has specified since 2026-09-06 was attempted. It is
not finished, but the attempt produced three things worth more than a partial
result: a working harness, a captured hang, and two ways of measuring this that
produce confident nonsense.

### The hang, caught live at delay = 30 s

```
[  196.479853] mt7615e 0000:01:00.0: mediatek/mt7663pr2h.bin not found, switching to mediatek/mt7663pr2h_rebb.bin
[  197.081018] mt7615e 0000:01:00.0: HW/SW Version: 0x65322d31, Build Time: 2009041715da1a1
[  197.081018]
```

Nothing after that. Confirmed whole-system, by both tests this project uses to
tell a hang from a wedge or a bad cable: **ping is 100% loss** *and* **the
console does not echo a known marker**. So a 30 s deferral does not avoid it,
which is consistent with the 20 s arm this file already records as 2 hangs in 4.

### ⚠️ Trap 1: score the boot AFTER the load, or you measure nothing

With the shipped `zx-wifi-late` (START=99, `sleep 30`), the firmware load fires
at **t ≈ 196 s**. A six-boot run scored at a 110 s settle window returned
**6/6 PASS, 0 hangs** - and every one of those verdicts was recorded *before the
load had happened*. The run measured the absence of an event that had not
occurred yet.

**Any sweep must use a settle window comfortably past the load**, which for the
shipped arm means ≥ 240 s, and must be recomputed whenever the delay changes.
A 120 s arm needs ~300 s. This is the single easiest way to produce a confident
false negative here, and it is exactly the shape of error this file's earlier
retractions took.

### ⚠️ Trap 2: do not score "booted" from a login banner

The console auto-logs-in once and prints no banner on subsequent boots, so
matching `Please press Enter` / `root@OpenWrt` scored perfectly healthy boots as
NOBOOT. Score by **active probe** instead - send a marker, require it back
intact. `boot-trial.sh` now does this, and it doubles as the cable-fault check.

### The harness

`../boot-trial.sh` runs N cold boots and emits one machine-parseable line each:

```
TRIAL arm=<label> boot=i/N verdict=PASS|FWHANG|NOBOOT|INCONCLUSIVE shell=up|down net=up|down bytes=<n>
TRIALSUM arm=<label> n=N pass=.. fwhang=.. noboot=.. inconclusive=..
```

INCONCLUSIVE exists so an instrument failure (no console output at all) is never
counted as a device failure - the mistake that withdrew a whole arm on
2026-09-06.

`../wifi-delay-sweep.sh` alternates two delay arms rather than batching them,
and proves each arm took before booting it. **Its weak point is the arm-setter:**
it edits `/etc/init.d/zx-wifi-late` over the UART, and on a bench where long
commands are lossy it repeatedly failed to confirm and burned boots on
SETUPFAIL. Anyone continuing should make the delay come from a file the init
script fetches over TFTP at boot instead, so changing arms needs no console at
all.

### ⚠️ Trap 3: do not let the settle loop exit early

The first fix for Trap 1 was to pass a longer settle window. It changed nothing,
because the loop **broke out as soon as it saw a shell marker and 60 s had
passed**. Two further runs - 6 boots and 4 boots - came back "all PASS, zero
hangs", and in neither did the firmware load happen at all before scoring:
`grep -c "HW/SW Version"` across the whole run was **zero**. A long window is
useless if something exits it early. `boot-trial.sh` now waits the full window
unconditionally and refuses any window below 240 s outright.

### The first valid measurement

With all three traps fixed, four cold boots at delay = 30 s:

| boot | verdict | shell | net |
|---|---|---|---|
| 1 | **FWHANG** | down | down |
| 2 | PASS | up | up |
| 3 | PASS | up | up |
| 4 | PASS | up | up |

**1 hang in 4** at 30 s. For comparison this file records 2 in 4 at the shipped
20 s, and `README.md` quotes 43/194 (22.2%) pooled across configurations.

Note `net=up` on the passing boots. Every earlier run reported `net=down`
throughout, and that was a symptom of scoring before the boot had finished, not
anything wrong with the device.

**Do not read 1/4 against 2/4 as an improvement.** Four boots cannot separate
25% from 50%; both are consistent with one underlying rate. What this run
establishes is that the harness now detects the event it is looking for, which
none of the three previous runs did.

### Status

**Not resolved.** The hang is reproduced, captured with its exact signature, and
now measurable. No arm has the ≥ 5 clean boots per arm the design calls for, and
the arm-setter needs the TFTP-fetched-delay rework before a full alternating
sweep can run unattended.
