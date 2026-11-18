> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Installing OpenWrt on the ZTE ZXHN H199A

**Read this whole page before touching the device.** Stock web installation
with the current bank-aware production kernel supports either running stock
bank; see [INSTALL-NO-UART.md](../INSTALL-NO-UART.md). The UART/TFTP recovery
procedure below explicitly writes physical bank A and preserves B. Native
upgrades use the selected running bank; see [BANKS.md](../BANKS.md).

The early sections retain historical bring-up results and commands. For current
acceptance results use [VALIDATION.md](../../VALIDATION.md); for the production
layout use §12 with the bank-aware changes below. In particular, current
production uses on-die ECC, UBIFS, and wired SSH/LuCI.

---

## 1. What you get, and what you do not

Be clear about this before opening the case. This is a port in progress, not a
finished firmware.

| Function | Status |
|---|---|
| Boot from NAND, MTD partitions | **works** |
| Configuration persistence across power cycles | **works; rate not reliably measured** (the soak scored unmeasured boots as failures, so the ~75% figure understates it and a clean run was never completed). JFFS2 on raw MTD with no ECC reverts rather than errors - treat config as expendable |
| Wi-Fi 5 GHz AP | **works for reaching the device** - Master/VHT80/24 dBm; association + DHCP + client-to-device traffic verified on the CURRENT image (round 239). Does **not** forward clients to the wired LAN (round 240) |
| Ethernet: ARP, ICMP, UDP, DHCP, DNS | **works, and at a moderate rate it is reliable** - ~99.8% delivery measured at 2 ms spacing (0.125-0.25% loss over 800/1200/1500-frame bursts, zero driver errors). But a sustained *flood* wedges the receive path permanently until a power cycle - see below. The older "~50-57% delivery" figure is retracted |
| **Multiple Ethernet ports** | Four netdevs, `eth0..eth3` == `mac0..mac3`, each with its own PHY and stable unique MAC. eth0 uses a factory address; the others use derived local addresses to avoid radio MAC collisions. Final-image all-port regression remains pending |
| **Switching between wired ports** | **works** - a normal bridge. The hairpin hotplug script is **gone**; with a netdev per port it would be a loop |
| **Routing + NAT between two ports** | **works** - verified end to end. `split_ports` is now the default and `board.d/02_network` ships `eth0 eth1 eth2` as lan, `eth3` as wan |
| **Ethernet: INBOUND TCP** | Vendor-derived selector fix restores SSH and payload in diagnostic RAM images. Bulk retransmissions/stalls remain; not yet a production-ready wired path |
| Ethernet: outbound TCP from the device | **works**, payload included |
| Boot reliability | **poor.** Boots hang at the Wi-Fi firmware load; the driver is kept out of kmodloader and loaded late, which moves the hang past userspace but does not remove it (2 hangs / 4 boots). Power-cycle and retry |
| **SSH / LuCI / `opkg`** | **work over Wi-Fi, not over Ethernet.** Verified on hardware: from a 5 GHz client, `nc -vz 192.168.1.1 22` succeeds and `curl http://192.168.1.1/` returns HTTP 200 with LuCI's HTML, while the wired host times out on both in the same session. `luci` ships in the image. **But see the stability caveat below - only one of three trials completed before the device wedged** |
| 2.4 GHz Wi-Fi | **works** - MT7603E behind PCIe port 1. AP on channel 6 (2.437 GHz), a client associates, gets a DHCP lease and passes traffic at 0% loss, and LuCI is reachable over it. Both radios carry their factory MACs from the `tag` partition (the vendor's own assignment). TX power is a regulatory default, not calibrated - there is no EEPROM for this radio and its eFuse is empty. See `docs/WIFI.md` |
| SMP (second CPU core) | **works** - both cores brought up via the vendor IRAM holding pen |
| sysupgrade | **works** - validated, executed (130 flash blocks rewritten) and booted. Image must be staged into flash first (the network cannot carry 17 MB). `-n` does NOT reset config, because the overlay partition is never written |
| Reset button, LEDs | absent - no GPIO driver |
| WAN / GPON uplink | GPON unsupported; an **Ethernet** WAN port works (routing/NAT verified) |
| Ethernet UDP throughput | **bounded by the wedge, not by the link.** There is no fixed per-boot frame budget - the device passed 3677 cumulative frames at 2 ms spacing in perfect health - but a sustained flood wedges the receive path (observed stopping points 3069 and 5115, both exact multiples of the 1023-slot ring). Device-side measurement gave 5.85 Mbit/s over one window; treat it as a floor set by the wedge |
| Wi-Fi throughput | **never measured.** A 5 GHz client did associate at a VHT80 link rate of 433.3 Mbit/s, but a link rate is not goodput |
| NAND error correction | **none** - see below |

### The datapath wedges under sustained load

**This is the limit that matters in practice.** Under a sustained high rate the
Ethernet receive path stops permanently: 100% packet loss in both directions,
and **only a power cycle recovers it**. Verified reproducible; `ifconfig
down/up`, a fabric reset, a full datapath re-init and re-priming the entire
buffer pool all fail to revive it.

**Reproduce it in one command** (round 251), from a freshly booted device:

```sh
sudo ping -f -c 4000 -s 1400 192.168.1.1
```

The trigger is **offered rate, not cumulative frame count.** The previous
statement of this limit - "after roughly 3000 received frames" - is withdrawn:
at 2 ms spacing the device passed **3677 cumulative frames with 0.2% loss and
zero errors**, well past the supposed threshold, and kept going. A flood kills
it; a moderate rate does not.

The wedge count is strikingly regular. Measured stopping points:

| observation | `rx_packets` at wedge | equals |
|---|---|---|
| round 178 | 3069 | **3 x 1023** |
| round 251 (twice, on two different firmwares) | 5115 | **5 x 1023** |

The RX ring holds 1024 descriptors with slot 0 reserved for TX, so 1023 are
usable for receive, and both wedge counts are **exact multiples of one ring
traversal**. That also argues against simple buffer-pool exhaustion (the pool
holds 2048 buffers and the device survives well past that).

**The wedge point is invariant under every driver knob.** Round 251 swept all of
them, each arm from its own cold boot, and the device wedged at 5115 every time:

| knob | values tried | effect on wedge point |
|---|---|---|
| `rx_release` | 0, 1, 2 (up to zeroing the whole descriptor) | none |
| `rx_credit_reg` | 0x168, 0x16c, 0x170 | none |
| credit-deficit repay | on, off | none |
| `rx_full_ring` (scan all 1024 slots) | on, off | none |

Nothing the driver does to the descriptors, the credit register or the ring
cursor moves the failure point. That points at a limit enforced on the hardware
side, reachable only with a register map this project does not have. Open lead
and full method: `research/ROUND-251-RING-TRAVERSAL-LEAD.md`.

### What the delivery rate actually is

At a moderate rate the datapath is **reliable**, not marginal. Measured on the
current image with device-side counters, each burst from a settled device:

| burst | host-visible loss |
|---|---|
| 800 x 100 B @ 2 ms | 0.125 % |
| 1200 x 100 B @ 2 ms | 0.25 % |
| 1500 x 100 B @ 2 ms | 0.2 % |

`rx_errors`, `rx_dropped` and `tx_errors` were **0** throughout.

This **retracts the "~50-57% delivery (best 2262/4000)" figure** that appeared
here and in `README.md` and `ETHERNET.md`. That number was most likely the wedge
already in progress during a flood, recorded as though it were a steady-state
rate. Delivery below the wedge threshold is ~99.8%.

Under a flood the loss figure is not a rate at all - it is the wedge arriving
partway through the run, and how much gets through before it hits varies widely
between boots (measured: 0.075%, 0.175%, 22.65%, 29.4%, 72.6%, plus several runs
that wedged mid-flood).

What still works: DHCP, DNS, ARP, ICMP and small transfers - bringing the device
up and managing it. What does not: any sustained transfer. A 17 MB image is
about 12,000 frames, well past the wedge.

The older figure of "line rate, 999/1000 at 1400 B" was measured over 1000
frames and on a TFTP boot where the driver's own datapath init is skipped. It is
not representative and has been removed.

### The NAND has NO error correction

The SPI-NAND chip's on-die ECC (8 bits per 512 B) is **deliberately disabled** by
this driver, and nothing replaces it - there is no controller ECC and no software
ECC. Every bit flip in flash is therefore silent and uncorrected, and there is no
persistent bad-block table, so a block that fails a write is retried forever
rather than being retired.

The reasoning is sound for *reading* vendor-written data (on-die ECC is only
usable if the whole device is rewritten with it enabled), but it is not a safe
steady state for a filesystem being written - in particular the JFFS2 overlay,
which takes every configuration change. **Treat the configuration on this device
as expendable.**

### The TCP limitation, stated plainly

**TCP to the device does not work.** ICMP, UDP, ARP, DHCP and DNS reach the CPU;
TCP does not terminate. In the most recent controlled test (round 233) real TCP
SYNs produced no driver-level count (`tcp_bare=0`, measured upstream of the
firewall) and connections did not establish at all.

The exact shape of the block is boot-path-specific and not fully explained: on
historical `cspboot` boots, payload-free TCP (SYN/ACK/FIN/RST) did reach the
driver (`tcp_bare` climbed to 12) while payload-bearing TCP never did
(`tcp_data` has never been non-zero); on a manually-booted diagnostic kernel, no
TCP reached the driver at all. Either way the user-visible result is the same:
**no SSH, no LuCI, no opkg, no working TCP.** See `docs/ETHERNET.md` and
`research/SPA-CLASSIFIER-LEADS.md` for the investigation and the honest limits.

Consequences you will hit immediately:

* **No SSH, no LuCI, no `opkg`** over Ethernet.
* Because `br-lan` is a *software* bridge (there is no switch/DSA driver), Wi-Fi
  clients cannot reach the wired LAN through the device: round 240 measured
  Wi-Fi->wired unicast unusable: 87.5-100% client-visible loss, reproduced twice.
  (The wired path independently loses 15-35% even for the device's own traffic,
  so where the loss occurs is not established.) A client reaches the device
  itself, not hosts behind it.
* Install and recovery are UART + TFTP only.

Root cause and a continuation path are in `research/ZX279133-SIBLING-DRIVER.md`.

---

## 2. Prerequisites

* **A 3.3 V USB-UART adapter.** You cannot install this without one.
  Settings: **115200 8N1**, and connect **RX, TX, GND** only - not VCC.
* A TFTP server on a machine wired to a LAN port of the H199A.
  The bootloader uses `ipaddr=192.168.1.1`, so give the host **192.168.1.100/24**.
* The build artifacts (see *Building*), or a prebuilt set of
  `kernel` / `rootfs` / `header`.

### Recovery, before you start

**Take a full backup of your device's flash before anything else.** It is the
only way to recover per-unit data (serial number, Wi-Fi calibration, SSID and
key) if something goes wrong, and it is what makes the staging-region check in
§11 possible.

The device has two firmware banks. **This procedure only ever writes bank A.**
Bank B holds the stock ZTE firmware and is the recovery path: if bank A's header
fails its CRC, the bootloader falls back to bank B automatically and boots stock.

A full stock boot was observed **once** to leave the OpenWrt partitions
byte-identical. That is one observation, not a guarantee - re-verify with
`cmp.b` after any stock boot before relying on bank A.

**Never write bank B** (`0x2000000`, `0x2300000`, `0x3020000`) or the bootloader.
Doing so removes your only recovery route.

---

## 3. Extracting your header template (required before building)

The bootloader validates a 128 KiB **header block** that carries CRC32s of the
kernel and filesystem areas *and* your unit's vendor fields. The build needs a
copy of your device's own header block as a template - it is device-specific, so
no template is shipped here, and using someone else's would push their unit's
identity onto your hardware.

**A per-unit-agnostic path exists and is being finished.** Only three words in
the header are derived; every other byte is the unit's own and must be kept.
`/usr/sbin/h199a-header-regen` (built from `tools/h199a-header-regen.c`) reads
the board's current header and rewrites just those three:

```
+0x3c   CRC-32 of kernel[0x20 .. 0x20+0x2ffdcc]
+0x48   CRC-32 of rootfs[0 .. 0xd20000]        (fixed, not the actual length)
+0xa4   CRC-32 of hdr[0 .. 0xa4]               (last: the two above are inside it)
```

so one public image could install on any unit instead of carrying a template
extracted from one. It is **installed but not yet called by `platform.sh`**:
the boot path changes only after the tool has been run against a real header on
the bench. `tests/test_header_regen.py` already proves it agrees with
`tools/flash-prep.py` byte for byte on the host. Until the wiring lands, the
template route below is still what the build uses.

**Partially verified on hardware, 2026-11-16.** The header block was read from
`mtd8` on the unit and the self-CRC checked directly:

```
stored   self-CRC @0xa4 = 0x513c6d71
crc32(hdr[0:0xa4])      = 0x513c6d71     MATCH
kernel CRC @0x3c = 0xf34ffb20
fs     CRC @0x48 = 0x35d58d58
version string @0x10: "V9.1.0P3N2_MUL"
vendor string  @0x6a: "ZXHN H199AV91"
```

So the block is where the contract says it is, the self-CRC convention is
right, and the device-specific fields are identifiable and must be preserved.
The kernel and filesystem CRCs still need checking, which needs the tool on a
bootable rootfs - the diagnostic RAM boot mounts the NAND rootfs read-only, so
it has the old rootfs without the tool. A `normal-ram-root` build (release
kernel plus a separately loaded squashfs) is the way to finish this without
touching flash.

There are two ways to get it off the device. **`tftpput` does not exist in this
bootloader** (verified on hardware: `Unknown command 'tftpput'`), so do not
expect to push it out from U-Boot.

**Method 1 - from Linux, if the device already runs any OpenWrt.**

```sh
H=/dev/$(sed -n 's/^\(mtd[0-9]*\):.*"header"/\1/p' /proc/mtd)
dd if=$H of=/tmp/header-template.bin bs=131072 count=1
```

Then copy it off. **TCP does not work on this device**, so `scp` and `wget` are
not options - use the busybox TFTP *client*, which is UDP and works:

```sh
tftp -p -l /tmp/header-template.bin 192.168.1.100
```

**Method 2 - from U-Boot, first install, no OS yet.** Read the block into RAM
and dump it over the serial console, then convert the hex back to binary on your
host:

```
=> nand read 0x42000000 0x1720000 0x20000
=> md.b 0x42000000 0x20000
```

128 KiB over a console is slow but needs nothing except the cable you already
have.

### In-band file transfer (once OpenWrt is running)

TCP does not work on this device, so `wget`, `scp` and `opkg` are all unavailable.
**TFTP works** - it is UDP, the transport this hardware handles best (though
see the delivery figures above: it is not line rate) - and the
busybox client is included:

```sh
cd /tmp && tftp -g -r <file> 192.168.1.100      # fetch
tftp -p -l /tmp/<file> 192.168.1.100            # send
```

Verified on hardware for a small file: the fetched digest matches the host byte
for byte. **Large transfers do not complete** - a 17 MB image is roughly 12,000
frames and the datapath wedges at ~3000 (see above), so the transfer stalls and
the device needs a power cycle. Block-size negotiation (RFC 2348) is enabled,
which reduces round trips but does not raise the frame budget.

> **Do not** try `nand read 0x42000000 0x0 0x8000000` for a whole-device backup.
> This board has 128 MiB of DRAM at `0x40000000-0x48000000`, so a 128 MiB read
> placed at `0x42000000` runs 32 MiB past the end of RAM. Read in chunks that
> fit.

`flash-prep.py` accepts either a full NAND dump of your device or just this
128 KiB header block. Keep the file you extract - the build needs it every time,
and it carries your unit's identity, so do not use someone else's.

## 4. Building

```sh
git clone <this repo>
cd openwrt-zte-h199a
H199A_HEADER=/path/to/header-template.bin ./build.sh
```

`build.sh` checks out OpenWrt 24.10 pinned at `a1ea57bd`, applies the `files/`
overlay and `seed.config`, and builds. Output:

```
openwrt/bin/targets/armsr/armv7/openwrt-armsr-armv7-zte_h199a-squashfs-sysupgrade.tar
```

containing `h199a/kernel`, `h199a/rootfs` and `h199a/header`.

> **Rule learned the hard way:** always run `build.sh` (or at minimum
> `cp -a files/. .` inside the OpenWrt tree) before a build whose output you will
> flash. Editing `build_dir/` directly is fine for iteration, but that output is
> not the recipe's, and treating it as such hid a months-old stale DTS for a long
> time (round 143).

Extract the three parts for flashing:

```sh
mkdir -p /tmp/h199a && tar xf openwrt-armsr-armv7-zte_h199a-squashfs-sysupgrade.tar -C /tmp/h199a
cp /tmp/h199a/h199a/{kernel,rootfs,header} /srv/tftp/
```

---

## 5. Partition layout

The full map, so nothing you are told to erase is missing from it:

| Label | Offset | Size | Notes |
|---|---|---|---|
| `bootloader` | `0x0000000` | 1 MiB | **do not touch** |
| `tag` | `0x0100000` | 1 MiB | per-unit data: serial number, SSID, Wi-Fi key |
| `wifi` | `0x0200000` | 1 MiB | radio calibration, read via a DT phandle at `+0x20000` |
| `usercfg` | `0x0300000` | 2 MiB | vendor config |
| `defcfg` | `0x0500000` | 2 MiB | vendor defaults |
| **`kernel1`** | `0x0700000` | `0x300000` | **bank A - written by this guide** |
| **`rootfs`** | `0x0a00000` | `0xd20000` | **bank A** |
| **`header`** | `0x1720000` | `0x20000` | **bank A CRCs - write LAST** |
| `kernel2` | `0x2000000` | 3 MiB | **bank B - stock. Never write this: it is your recovery** |
| `rootfs2` | `0x2300000` | 13 MiB | bank B - stock |
| `rootfs_data` | `0x4000000` | 16 MiB | JFFS2 overlay (your configuration) |
| `staging` | `0x5000000` | 20 MiB | sysupgrade images - **verify it is erased on YOUR unit first**, see §11 |

Gaps not covered above are not automatically free: `0x03000000-0x04000000` holds
high-entropy vendor data on the author's unit.

The **header** holds CRC32s of the kernel and filesystem areas and is what the
bootloader validates. Write it **last**: until it is updated it still describes
the old kernel, so an interrupted flash leaves bank A invalid and the device
falls back to stock rather than bricking.

---

## 6. Flashing

Power on with the serial console attached and interrupt the bootloader to get the
`=>` prompt.

**Every partition is written the same way: TFTP, erase, write, then READ IT BACK
AND COMPARE.** The comparison is not optional - see the note directly below for
why. Do the three in this order; the header last is what makes an interrupted
flash recoverable.

```
=> tftp 0x42000000 kernel
=> nand erase 0x700000 0x300000
=> nand write 0x42000000 0x700000 0x300000
=> nand read  0x44000000 0x700000 0x300000
=> cmp.b 0x42000000 0x44000000 0x300000
   # REQUIRED: "Total of 3145728 byte(s) were the same"

=> tftp 0x42000000 rootfs
=> nand erase 0xa00000 0xd20000
=> nand write 0x42000000 0xa00000 0xd20000
=> nand read  0x44000000 0xa00000 0xd20000
=> cmp.b 0x42000000 0x44000000 0xd20000
   # REQUIRED: "Total of 13762560 byte(s) were the same"

=> tftp 0x42000000 header
=> nand erase 0x1720000 0x20000
=> nand write 0x42000000 0x1720000 0x20000
=> nand read  0x44000000 0x1720000 0x20000
=> cmp.b 0x42000000 0x44000000 0x20000
   # REQUIRED: "Total of 131072 byte(s) were the same"
```

If any comparison reports a smaller total, **the write did not land** - re-erase
and rewrite that partition before continuing. A smaller number is the *offset of
the first difference*, not a count of matching bytes.

### Verify every step - `bytes written: OK` is not proof

**This is the single most important instruction in this document.** This flash
has no ECC and no bad-block retirement, so nothing underneath will detect or
correct a write that did not land. `nand write` reporting `OK` means the
controller accepted the data; it does **not** mean a later read returns it.
During development three partitions in one session failed to contain what had
been written to them, each presenting as a different and confusing symptom.

**After every `nand write`, read it back and compare:**

```
=> tftp 0x42000000 <part>.bin
   # confirm: Bytes transferred = <exact size>

=> nand erase <off> <len>
   # confirm: 100% complete, and NO "Skipping bad block" lines

=> nand write 0x42000000 <off> <len>

=> nand read 0x44000000 <off> <len>
=> cmp.b 0x42000000 0x44000000 <len>
   # REQUIRED: "Total of <len> byte(s) were the same"
```

Anything else means the write did not land - re-erase and rewrite. Note that a
**smaller total is the OFFSET of the first difference, not a count of matching
bytes**: `cmp.b` stops at the first mismatch. This U-Boot has no `crc32`, so
comparing against the freshly TFTP'd copy still in RAM is the only in-bootloader
check available.

U-Boot reports success even when blocks fail, and a failed TFTP leaves the
previous buffer contents in RAM, which then get written happily. **Check that
each `tftp` prints the byte count you expect** before running the matching
`nand write`:

```
Bytes transferred = 3145728 (300000 hex)
Bytes transferred = 13762560 (d20000 hex)
Bytes transferred = 131072 (20000 hex)
```

A mismatch here means you are about to flash garbage. This exact failure happened
in round 165: the artifacts had not been generated, TFTP fetched nothing, the
erase ran anyway, and the bootloader correctly rejected the result and booted
stock.

Once booted, verify the partitions from Linux:

```sh
cat /proc/mtd                   # confirm the labels are present
K=/dev/$(sed -n 's/^\(mtd[0-9]*\):.*"kernel1"/\1/p' /proc/mtd)
R=/dev/$(sed -n 's/^\(mtd[0-9]*\):.*"rootfs"/\1/p' /proc/mtd)
md5sum $K $R
```

---

## 7. First boot and persistence

```
=> reset
```

Two things to expect:

1. **Configuration persists only from the second boot onward.** The first boot
   formats the JFFS2 overlay; the second adopts it. Testing persistence after a
   single boot will look like failure.
2. The overlay lives on a raw MTD volume. If `rootfs_data` is ever erased, it
   must be re-seeded with a `deadc0de` marker page, otherwise `fstools` reads it
   as `FS_NONE`, silently falls back to a tmpfs overlay, and nothing persists:

Run this **on the device**, and look the partition up by label - never hardcode
an mtd number. They have already shifted once in this project's history, and
writing the seed to the wrong partition destroys it:

```sh
SEED=/dev/$(sed -n 's/^\(mtd[0-9]*\):.*"rootfs_data"/\1/p' /proc/mtd)
echo "seeding $SEED"
dd if=/tmp/rootfs_data of=$SEED bs=2048 count=1
```

(`tools/flash-prep.py` emits the `.rootfs_data` seed page alongside the other
artifacts; copy it to the device's `/tmp` first, or write it from U-Boot.)

Confirm persistence:

```sh
echo test > /etc/persist-check ; sync ; reboot
# after reboot:
cat /etc/persist-check          # should print "test"
readlink /overlay/.fs_state     # reaches 2 after two boots
```

---

## 8. Bringing up Wi-Fi

```sh
uci set wireless.radio0.disabled=0
uci set wireless.radio0.country=<your ISO code>
uci set wireless.default_radio0.ssid=<your ssid>
uci set wireless.default_radio0.encryption=psk2
uci set wireless.default_radio0.key=<your passphrase>
uci commit wireless
wifi up
```

Verify:

```sh
iwinfo phy0-ap0 info            # expect Master, VHT80, 24 dBm
iw dev phy0-ap0 station dump    # after a client associates
```

Calibration data is read from the `wifi` partition at `+0x20000` via the DT
`mediatek,mtd-eeprom` phandle (no mtd number is hardcoded anywhere)
property; without it the radio comes up at reduced power.

---

## 9. Recovery, verified end to end

The two-bank fallback was tested on hardware, not assumed:

1. **Erase bank A's header** (`nand erase 0x1720000 0x20000`) - simulating an
   upgrade interrupted before the header is written. The device boots **stock
   firmware** (`H199A V9.1 login:`). Recovery works.
2. **Restore bank A** and it boots OpenWrt again, with the JFFS2 overlay
   configuration still intact throughout. To restore, **re-run §6 in full** -
   flash all three parts (kernel, rootfs, then header LAST) from the *same* build,
   each with its `cmp.b` read-back check. Restoring only the header does not work
   (see the trap below).

**Which bank booted?** Read the UART banner: stock is `H199A V9.1 login:`;
OpenWrt reaches `root@H199A-P130:~#`. If you see the stock banner, bank A was
rejected and you are on the recovery firmware.

### The trap: a header alone is not a restore

Restoring only the header does **not** bring bank A back unless that header
matches the kernel *and* rootfs currently on flash. After a `sysupgrade`, flash
holds the image's kernel and rootfs, so an older header - even a valid,
self-consistent one - is rejected:

```
csp_crc: data addr:42000000, crc_len:0xa4
crc=0x28c5a688, 0xd73a5977          <- computed vs expected
```

The bootloader finds the header and tests bank A, then refuses it. Restore all
three parts from the **same** image, or keep the matching header alongside every
kernel you flash.

## 10. Recovering to stock

Nothing in this procedure damages bank B, so:

* If bank A is invalid, the bootloader boots stock automatically.
* To force it, erase bank A's header: `nand erase 0x1720000 0x20000`.

---

## 11. Upgrading with sysupgrade

* **`sysupgrade` works, but the image cannot be fetched over the network** (a
  17 MB transfer is far beyond what the datapath sustains). Stage it into the
  `staging` partition from U-Boot first:

  **First, verify the staging region is empty ON YOUR DEVICE.** It was confirmed
  erased on one unit only, and this family stores per-unit data in flash (the
  author's dump contains its serial number, SSID and Wi-Fi key). A unit with
  different or upgraded firmware may hold something at this address, and the
  next command erases 20 MiB unconditionally:

  ```
  => nand read 0x42000000 0x5000000 0x20000
  => md.l 0x42000000 0x40
  ```

  Every word must read `ffffffff`. If anything else appears, **stop** - pick a
  different region (the author's dump also shows `0x01740000-0x02000000` erased,
  8 MiB, enough for a smaller image) and adjust the DTS partition accordingly.
  Note `0x03000000-0x04000000` is **not** free on the author's unit: it holds
  high-entropy vendor data.

  ```
  => tftp 0x42000000 <image>-sysupgrade.tar
  => nand erase 0x5000000 0x1400000
  => nand write 0x42000000 0x5000000 0x1060000     # round UP to a block multiple
  ```

  then, on the running system:

  ```sh
  S=/dev/$(sed -n 's/^\(mtd[0-9]*\):.*"staging"/\1/p' /proc/mtd)
  # Size the read from the image itself rather than hardcoding it: a larger
  # image would otherwise be silently truncated, and sysupgrade -T can still
  # accept a truncated tar.
  SZ=$(( ($(stat -c%s /path/to/image-on-your-host) + 1023) / 1024 ))
  dd if=$S of=/tmp/sysupgrade.tar bs=1024 count=$SZ
  md5sum /tmp/sysupgrade.tar        # compare against the host copy
  sysupgrade -T /tmp/sysupgrade.tar # validate first
  sysupgrade /tmp/sysupgrade.tar
  ```

  The device halts instead of rebooting at the end ("Reboot failed -- System
  halted"); power-cycle it. Configuration is preserved by default.
* **Do not mark the rootfs partition `read-only` in DT.** It blocks the char
  device too, so `mtd write` fails. Use `CONFIG_MTD_BLOCK=n` +
  `CONFIG_MTD_BLOCK_RO=y` instead, which is what this tree does.
* **Do not expect `tcpdump` on the device to prove anything about RX.** The
  driver hands frames up via `napi_gro_receive`; capture from the peer instead.


## ⚠ Flashing a new rootfs does NOT update any file that has been edited on the device

Found on 2026-09-07, after four images in a row silently ran an old init script.

The overlay is JFFS2 on `rootfs_data`, mounted over the squashfs with overlayfs.
Flashing replaces the squashfs — the **lower** layer. Anything ever written on
the device lives in the **upper** layer and keeps shadowing the shipped file
forever. `sysupgrade` preserves the overlay by design; a manual bank-A flash
does not touch it at all.

On this bench the upper layer held, among others:

```
/overlay/upper/etc/init.d/zx-wifi-late          <- an old copy from a sed'd experiment
/overlay/upper/etc/modules.d/mt7603
/overlay/upper/etc/modules.d/mt7615e            <- a CHARACTER DEVICE, i.e. a whiteout
/overlay/upper/etc/modules.d/.mt7615e-deferred  <- the original, renamed by an experiment
```

The consequences were not cosmetic. The reworked `zx-wifi-late` — which reads
its arm from `/etc/zx-wifi-delay` and announces it on the console — shipped in
four images and ran in none of them, because a copy edited weeks earlier
shadowed it. `grep -c ARM /etc/init.d/zx-wifi-late` returned 0 on a device whose
squashfs demonstrably contained the new script (checked with
`tar xzf ...-rootfs.tar.gz ./etc/init.d/zx-wifi-late`).

**How to check** — list what the overlay is hiding:

```sh
find /overlay/upper -type f      # shadowing copies
find /overlay/upper -type c      # whiteouts: files DELETED from the shipped image
```

**How to fix, surgically.** Delete the *upper* copy, not the merged path — `rm
/etc/foo` on a merged mount creates a whiteout and makes things worse:

```sh
rm -f /overlay/upper/etc/init.d/zx-wifi-late
sync
# then power-cycle: the merged view is cached until remount
```

A `firstboot`/`jffs2reset` clears everything, but on this bench that also
discards `/etc/config/network`, which is what holds the static `192.168.1.1`
the whole rig depends on. Prefer the surgical form.

**Rule of thumb:** anything under `/etc` that an experiment has touched is
pinned at the value it had when it was touched, for every subsequent image,
until the upper copy is removed. Assume nothing in the rootfs updated just
because the flash verified.

---

## 12. Production profile (`BOOT_PROFILE=production`) — hardware-qualified 2026-11-15 (one unit)

Everything above describes the hand-driven bank-A flash and the earlier
JFFS2-on-raw-MTD overlay. The **production profile** packages that into a build
with a UBI overlay, a two-layer write policy and a verified sysupgrade. It
passed the full §12.7 ladder on the author's unit on 2026-11-15 (results in
§12.8). That is one unit: read it and run the ladder yourself before trusting
it on yours.

### 12.1 Build

```sh
H199A_MT7603_EEPROM=/private/MT7603E_EEPROM.bin \
H199A_HEADER=/path/to/header-template.bin \
BOOT_PROFILE=production JOBS=1 ./build.sh
```

Outputs under `openwrt/bin/targets/armsr/armv7/`:

- `…-zte_h199a-squashfs-sysupgrade.tar` — the factory/sysupgrade bundle
  (`h199a/kernel`, `h199a/rootfs`, `h199a/header`), consumed by
  `sysupgrade` and by the first U-Boot install (extract the three parts).
- `…-sysupgrade-parts/{kernel,rootfs,header}` — the same three parts loose,
  for a first U-Boot TFTP install.
- `…-sysupgrade-production.json` — the build-time validator's report: every
  CRC the bootloader checks, the fixed `fs_size`, and proof the header differs
  from your unit's template **only** in the three CRC fields (identity preserved).

The physical factory layout is unchanged. `flash-prep.py` and the guarded
first-install procedure in §6 still target A. For web installation, the vendor
chooses the inactive bank. For native upgrades, OpenWrt selects the running
bank; [BANKS.md](../BANKS.md) describes its validation and logical partition names.

### 12.2 The two-layer write policy

The selected bank plus the separate UBI overlay are writable. The peer bank,
bootloader, calibration, vendor configuration, old overlay and whole-flash
master remain read-only. Both MTD flags and a compiled SPI transport allowlist
enforce this, independently:

| Running bank | Firmware window | UBI window |
|---|---|---|
| A | `[0x00700000,0x01740000)` | `[0x05400000,0x06400000)` |
| B | `[0x02000000,0x03040000)` | `[0x05400000,0x06400000)` |

The bootloader selection is captured before the decompressor overwrites its
BootPara. Invalid selection fails closed. Active logical labels are always
`kernel1`, `rootfs`, `header`; peer labels end in `2`. The native transport
never permits both firmware windows, and its first policy refusal latches
until reboot. Exact rows and qualification behavior are in [BANKS.md](../BANKS.md).

### 12.3 ECC — resolved: production uses Micron on-die ECC

The design note calls the flash "no-ECC". That describes the **raw-NAND shim**
(`zx_spifc_nand.c`, `NAND_ECC_ENGINE_TYPE_NONE`), which was never enabled in the
production configuration and has since been deleted outright. The production path is the native SPI-mem transport
(`CONFIG_SPI_ZX279128`) under Linux's stock SPI-NAND core
(`CONFIG_MTD_SPI_NAND`), which selects the chip's **Micron 8-bit/512 B on-die
ECC** engine (`NAND_ECC_ENGINE_TYPE_ON_DIE`, `micron_8_ecc_get_status`):

- every non-raw page write enables ECC (`CFG_ECC_ENABLE`) and writes parity
  into OOB — so `mtd write` of bank A and every UBI write are ECC-protected;
- every non-raw read enables ECC and reports **per-request** status (0 / 3 / 6 /
  8-bit corrected, or `-EBADMSG` uncorrectable), feeding `ecc_stats`;
- the transport moves bytes only; it rejects host-ECC requests (`op->data.ecc`)
  and never changes the ECC mode itself.

The vendor bootloader also reads bank A with on-die ECC enabled (B0 = 0x18
includes ECC_EN), so its kernel/fs CRC check sees the same corrected logical
bytes `flash-prep.py` computed the CRC over. The round-231 "on-die ECC not
viable" note applied only to the raw shim (parity-less pages read with ECC on);
it does not apply here, where writes and reads both use ECC. Still verify every
bank-A write with a read-back `cmp` (§6): ECC corrects bit flips, it does not
make `nand write ... OK` proof on its own.

### 12.4 Overlay

The overlay is the UBI volume `rootfs_data` (dynamic, 104 LEBs) on the fenced
window `overlay_ubi` `[0x05400000, 0x06400000)`, already created and power-loss
qualified. `lib/preinit/78_h199a_production_overlay` attaches it (only in the
production image, recognised by `spi_zx279128.production=1`), creates
`rootfs_data` on a genuinely empty window, and **refuses to format a window that
holds an unexpected volume** — then hands it to fstools, which mounts
`ubi0:rootfs_data` as the overlay over the `/rom` SquashFS. This replaces the
raw-MTD `deadc0de` seed entirely; that marker is a raw-MTD artifact and is never
written into UBI.

### 12.5 sysupgrade

`lib/upgrade/platform.sh` checks board, archive sizes, active physical offsets
and kernel capability before shutdown. On B it refuses an old A-only kernel.
Before the first erase, the packaged header helper validates the unit's own
headers and payload and prepares a serial above both selectable banks.

It writes **rootfs → kernel1 → header LAST**, verifying each readback before
the next write. These labels resolve to the running bank. The peer firmware,
bootloader and calibration stay read-only. Configuration lives in the separate
UBI overlay; `-n` recreates only `rootfs_data`. A partial write can leave an
invalid active image and select a valid peer at the next boot. Fresh power-cut
qualification of the bank-aware image is not claimed.

Upload the sysupgrade tar to `/tmp` over LAN and run `sysupgrade -T` before
`sysupgrade`. Current wired transfers work; flash staging is unnecessary.
Never use `staging` `[0x5000000,0x6400000)` as scratch space: it contains the
UBI window. Detailed header validation and downgrade rules are in
[BANKS.md](../BANKS.md).

### 12.6 RAM-bootable production-policy qualification (`PRODUCTION_QUALIFY=1`)

```sh
H199A_MT7603_EEPROM=/private/MT7603E_EEPROM.bin \
H199A_HEADER=/path/to/header-template.bin \
BOOT_PROFILE=production PRODUCTION_QUALIFY=1 JOBS=1 ./build.sh
```

This builds a **RAM-root** image (`…-ram-rootfs.squashfs`, booted the same way
as normal-X) with the identical write policy compiled in but in
`spi_zx279128.production_qualify=1` mode and the `-production-qualify` DTS (bank
A writable at the MTD layer, master writable). In this mode the transport
**refuses every bank-A program/erase** while still allowing the UBI window, so
the full allow/deny matrix can be exercised on hardware **without writing bank
A**. Read `/sys/.../spi@94406000/zx279128-spifc/write_policy_map` for the
compiled matrix and `write_policy_state` for the latch/refusal counters.

### 12.7 Hardware qualification ladder (owner-executed; each gate aborts on failure)

> Every step is gated on the previous one passing and on owner sign-off before
> the **first** bank-A write. All six steps passed on one unit (§12.8).

1. **RAM production-policy deny matrix.** Boot `PRODUCTION_QUALIFY=1`.
   *Capture:* `write_policy_map`, `write_policy_state`, and an attempted
   program/erase to each protected partition returning `-EROFS`; confirm bank A
   is flagged writable (`/sys/class/mtd/*/flags`) but every bank-A write is
   refused and the latch trips once. *Abort if* any protected offset accepts a
   write, or bank A is programmed/erased.
2. **Fresh full NAND backup + outside-window verification.** Dump the whole
   corrected NAND; verify prefix `[0,93585408)` = `b8417e6e…` and suffix
   `[111411200,142606336)` = `59404267…` (codex-handoff §8) and bank B region
   hashes. *Abort if* any outside-bank-A hash differs from the pre-write backup.
3. **First bank-A install (owner sign-off).** Over U-Boot TFTP, flash
   rootfs → kernel1 → header (header LAST), each with `cmp.b` (§6). Immediately
   re-dump and confirm bootloader, `tag`, `wifi`, bank B, `legacy_overlay` and
   the window are byte-identical to step 2. *Abort if* any `cmp.b` is short or
   any outside-bank-A region changed.
   *Tool:* `tools/install-bank-a-uboot.py` drives exactly this from a closed
   19-command set derived from the three bank-A rows (no other offset, no
   env/saveenv/boot command). Each part is TFTP'd twice and the copies compared
   before the erase; each command line is typed without CR and only executed
   when the bootloader's echo is exactly the intended line (a corrupted digit
   is discarded with Ctrl-C, never executed); any skip/mark-bad/fail text
   aborts; it always ends with the router powered off.
4. **Boot-from-NAND acceptance.** `reset`; confirm the bootloader logs
   `correct header has been found @1720000`, `verify kernel success!!`,
   `verify fs success!!`, boots OpenWrt (not `H199A V9.1 login:`), attaches
   `ubi0:rootfs_data`, and config survives a power cycle. *Abort if* it falls
   back to stock or the overlay does not mount.
   *Tool:* `tools/nand-boot-observe.py` powers on and only listens (it
   holds the UART TX lock and writes nothing), requiring those markers in order
   and cutting power at once on firmware `[1]` (stock), a stock login, a panic
   or a verify/UBI/SquashFS error — stock never runs unattended.
5. **sysupgrade incl. power-loss injection.** Stage a new image into a
   verified-erased offset, `sysupgrade -T`, upgrade; confirm config preserved in
   UBI and bank B intact. Then repeat with power cut injected between the rootfs
   write and the header write. *Abort if* a power cut ever yields anything but
   old-OpenWrt or stock-fallback (never a brick), or bank B changes.
6. **Recovery drill.** Erase bank A's header (`nand erase 0x1720000 0x20000`) →
   confirm stock boots → restore all three parts → confirm OpenWrt returns with
   the overlay intact. *Abort if* stock does not come up, or restore does not
   return OpenWrt.

### 12.8 Ladder results (2026-11-15, one unit)

| step | result |
|---|---|
| 1 RAM deny matrix | writable exactly kernel1/rootfs/header/overlay_ubi; live policy map == spec model; `mtd erase kernel1` refused on every block, block 0 unchanged, latch tripped once, 0 bad blocks |
| 2 backup | full corrected dump twice-identical, 0 read errors; everything outside the UBI window identical to the earlier baseline |
| 3 first install | `tools/install-bank-a-uboot.py`: exact printed offsets/sizes, every `cmp.b` full length, 0 echo discards; re-dump: **every byte outside bank A identical**, bank A == the three parts, **0 read errors in the new bank A** (U-Boot writes valid on-die parity) |
| 4 NAND boot | `correct header … @1720000` → `[0]firmware` → verify kernel/fs success → `production=1` → squashfs root → **existing UBI overlay attached, not formatted**; migrated config intact; survives a hard power cut |
| 5 sysupgrade | v1→v2 keep-config: written+verified rootfs→kernel1→header, config and host keys preserved, re-dump clean. **Power cut during the kernel1 write → bootloader rejects bank A (kernel CRC) → selects stock bank B** (power was cut before stock ran) → U-Boot reinstall → clean |
| 6 recovery drill | `--erase-header-only` → stock bank B selected → reinstall → full dump byte-identical to before the drill → OpenWrt + overlay back |

Bootloader quirk found in step 6: `zteboot_verify_header` classifies a block
by the word at +4 (0 = firmware header, 1 = boot header). A UBI erase-counter
header has 1 there, so with one bank's header missing the search reports
`correct header has been found @5400000` (the first UBI PEB) as an *empty
boot-class* header. Firmware selection ignores that class, so the fallback
still boots bank B. A UBI block can never pass as a firmware header. See
[NAND.md](../NAND.md).

Qualification tooling: `tools/install-bank-a-uboot.py` (steps 3 and 6,
`--erase-header-only`), `tools/verify-install-dump.py` (compares a post-change
full corrected dump with the pre-change one, both outside bank A and in its
contents), `tools/nand-boot-observe.py` (step 4) and `tools/sysupgrade-observe.py`
(step 5; passive, cuts the outlet at a chosen `h199a:` write message, anchored
on a per-run nonce echoed by the launch command).

**Not exercised on the unit:** `sysupgrade -n` (it recreates `rootfs_data`
and would have destroyed the owner's migrated configuration; host-tested only).
