> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](README.md),
> [installation](INSTALL.md) and [validation](../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# ETHERNET - investigation journal

> **This is a chronological record, not a description of the current system.**
> It contains hypotheses that were tested and later **withdrawn**; several
> confident conclusions here are wrong and are corrected further down.
>
> For what is true now, read [`ETHERNET.md`](ETHERNET.md).
>
> It is kept because the failure modes proved more reusable than the results:
> instruments that could not fire, controls that did not exist, fixes validated
> against something the build does not produce, and rig faults misread as device
> faults. Those mistakes are the most transferable thing here.

# Ethernet bring-up (ZX279128S / ZXHN H199A)

## Status

| layer | state |
|---|---|
| MDIO bus | ✅ working — driver written, PHYs detected on hardware |
| GE PHYs | ✅ four found at MDIO addr 10-13, ID `84b9:5031` |
| MAC register map | ✅ decoded + hardware-verified (`0x92200000`, stride `0x40000`) |
| Buffer manager | ✅ decoded + verified enabled (`0x92348000`) |
| Traffic manager | ✅ decoded + live credits seen (`0x92350000`) |
| Buffer pool memory | ✅ `0x41000000` 4 MiB, reserved in DT and confirmed |
| Descriptor format | ✅ 16 B, bit-packed idx/len; RX ring 1024 entries |
| netdev driver | ⚠️ **PARTIAL** — see the blocker directly below |

> ## Historical failure snapshot: TCP payload did not pass in that candidate
>
> ICMP, UDP, ARP, DHCP and DNS all work, at any frame size and at line rate
> (999/1000 unpaced 1400 B UDP frames; DNS answered at 2000 queries/s). **But
> every TCP connection establishes and then stalls**, in both directions, for a
> response as small as five bytes.
>
> The SoC's packet classifier steers TCP segments *carrying payload* into a
> hardware forwarding flow that never reaches the CPU, while payload-free TCP
> (SYN, SYN-ACK, ACK, FIN, RST) is delivered normally. Measured inside the
> driver, counting arrivals by IP protocol:
>
> ```
> census icmp=0 udp=48 tcp_bare=12 tcp_data=0
> ```
>
> `tcp_data` has never been anything but zero. Consequences: **no SSH, no LuCI,
> no opkg**, and - because `br-lan` is a software bridge with no switch/DSA
> driver - Wi-Fi clients' downstream TCP very likely traverses the same path
> (unmeasured).
>
> Mechanism and a continuation path: `research/ZX279133-SIBLING-DRIVER.md`.
> The sections below are a chronological investigation journal and contain
> hypotheses that were later **retracted**; the table above and this box are the
> the interpretation at that point, superseded by later entries and the current guide.

## Why U-Boot is the reference, not the stock kernel

The Linux-side vendor Ethernet driver is **not** in the stock `vmlinux`: there
are no `zte,zx279128s-{npp,pp,pon}` compatibles or NPP symbols there (see
`docs/BRINGUP.md`). It lives in the encrypted `"SBU&"` rootfs.

The **bootloader does have working Ethernet** — TFTP runs at ~10 MiB/s — and the
bootloader partition is plain (unencrypted) in `h199a-firmware/mtd0-bootloader.bin`. So
U-Boot is the practical RE source. Relevant strings:

```
0x5e194  gmac read sucess!          0x5f5df  gpon serdes init
0x5e1a7  279112mdio                 0x5f7a6  mac %d phy status changed: %s %s
0x5f5cc  epon serdes init           0x5f7c8  -----smac_init
```

Word-aligned literals show which blocks U-Boot drives:

| block | address | file offset of literal |
|---|---|---|
| mdio | `0x9a101000` | `0x401c8` |
| npp  | `0x921c0000` | `0x51100` |
| tm   | `0x92340000` | `0x500f8`, `0x50580` |
| pp   | `0x92380000` | `0x50cf8` |

(So even U-Boot's minimal path goes through the NPP/PP packet processor — this
is not a plain GMAC. But U-Boot only does enough for TFTP, which is exactly the
subset a first Linux driver needs.)

## MDIO register map (decoded from U-Boot, base `0x9a101000`)

```
+0x04  W   write data (16-bit)
+0x08  R   read data  (16-bit)
+0x10  RW  status: bit0 = transfer done; write 0 to clear
+0x14  RW  control:
             bit14      start
             bits11:10  opcode - 0b10 (0x800) = read, 0b01 (0x400) = write
             bits9:5    PHY address
             bits4:0    register address
```

Vendor sequence (both read and write): clear start → clear status → set opcode →
set reg → set phy → (write: store data at `+0x04`) → set start → poll status
bit0 → clear status → clear start → (read: fetch `+0x08`).

Decoded from `mtd0-bootloader.bin` at file offsets `0x401cc` (read) and
`0x402c4` (write); the only difference between them is the opcode and the extra
`str r2, [r3, #4]` that stages the write data.

## Driver

`files/target/linux/armsr/files-6.6/drivers/net/mdio/mdio-zx279128.c`,
compatible `zte,zx279128s-mdio`, wired in by
`files/target/linux/armsr/patches-6.6/994-zte-mdio-driver.patch`
(`CONFIG_MDIO_ZX279128`). Note kernel 6.6 removed `MII_ADDR_C45` from the
`read`/`write` callbacks (C45 has its own `read_c45`/`write_c45`).

## Verified result

A probe-time bus scan (kept in the driver — it distinguishes a silent bus from
PHYs at unexpected addresses) found the PHYs are **not** at 0-3:

```
mdio-zx279128 9a101000.mdio: ZX279128S MDIO bus registered
mdio-zx279128 9a101000.mdio: scan phy10: id=84b9:5031
mdio-zx279128 9a101000.mdio: scan phy11: id=84b9:5031
mdio-zx279128 9a101000.mdio: scan phy12: id=84b9:5031
mdio-zx279128 9a101000.mdio: scan phy13: id=84b9:5031
```

With `ethernet-phy@10..13` in the DT the "MDIO device at address N is missing"
warnings disappear and phylib binds them.

Note the stock DTS gives the mdio node `clocks = <0x05 0x01>`; we do not model
that clock yet, so `clk_ignore_unused` is currently on the kernel cmdline to stop
Linux gating it off. Modelling the clock properly is a small follow-up.

## Next

1. Decode `smac_init` in U-Boot (file offset near the `0x5f7c8` string) to get
   the MAC/datapath bring-up: serdes init, port enable, and the descriptor rings.
2. Map the minimal NPP/TM/PP register writes U-Boot performs for TX/RX.
3. Write a `zx279128-eth` netdev driver using the PHYs above.

## U-Boot link base = `0x47edf800`

Needed for any further RE of the bootloader, and not obvious (U-Boot is
relocated). Solved by taking several known strings, forming the candidate set
`{word - file_offset(string)}` over every 32-bit word in the image, and
intersecting across strings — the single plausible common value is
**`0x47edf800`**, i.e.

```
vaddr = 0x47edf800 + file_offset
```

Cross-check: it puts the `47f3xxxx` literals seen in code exactly in range, and
resolves `-----smac_init` (file `0x5f7c8`) to `0x47f3efc8`, which is referenced
from a literal pool at file `0x51018`.

## MAC block (from `smac_init`)

The init code writes per-port registers with `str r2, [r3, r4, lsl #18]`, i.e.
**register base `0x92200000`, port index in `r4`, per-port stride `0x40000`**:

| port | base |
|---|---|
| 0 | `0x92200000` |
| 1 | `0x92240000` |
| 2 | `0x92280000` |
| 3 | `0x922c0000` |

(That range sits inside the stock DTS `pon@92000000` reg window.)

Init values observed in `smac_init`:

| offset | value |
|---|---|
| `+0x070` | `0x00300002` |
| `+0x0b4` | `0x00004000` |
| `+0x0e0` | `0x00011200` |
| `+0xb00` | `0x0010ff11` |
| `+0xd00` | `0x32` (50) |
| `+0xd30` | `0xa8` (168) |

Link state is polled through a separate block at **`0x921d9000`** (`+0x68` is
read and tested against a per-port bit mask), and the PHY status word is decoded
into a speed index (0/1/2 → 10/100/1000) and a duplex flag — this is what
produces the familiar `mac %d phy status changed: 1000M full-duplex` line.

Still missing for a netdev driver: the descriptor rings / DMA setup and the
NPP/TM/PP glue that actually moves frames. Those are the next targets.

### Hardware check of the MAC map

The map above was validated on the running board by dumping those registers from
the MDIO driver's probe (temporary bring-up aid, kept in the driver):

```
mdio-zx279128 9a101000.mdio: mac0 +070=00300002 +0b4=00004000 +0e0=00000000 +b00=0000ff01
                                       ^^^^^^^^        ^^^^^^^^
u-boot smac_init writes:               00300002        00004000     <- exact match
```

`+0x070` and `+0x0b4` read back exactly the values U-Boot programs, which
confirms both the base (`0x92200000`) and the offsets. `+0x0e0` and `+0xb00`
differ from the init constants (`0x00011200` / `0x0010ff11`), so those are
written later in the sequence or vary with port/link state — worth resolving
when the datapath is mapped.

### Poking registers from userspace

`CONFIG_DEVMEM=y` (with `STRICT_DEVMEM` off) is now enabled, so `/dev/mem`
exists on the target. Note `hexdump`/`read()` fails on MMIO with `Bad address`;
a small `mmap()`-based helper (like busybox `devmem`, not currently built into
our rootfs) is needed. Until then, the kernel-side dump above is the quickest
way to inspect registers.

## Datapath architecture (from U-Boot's eth_device)

U-Boot's driver registration (`malloc(64)` then the standard `eth_device`
layout) gives the entry points directly:

| field | offset | address |
|---|---|---|
| `init` | +0x20 | `0x47f2fde4` |
| `send` | +0x24 | `0x47f301f8` |
| `recv` | +0x28 | `0x47f2feb4` |
| `halt` | +0x2c | `0x47f2fe14` |

Reading `send` shows this is **not** a classic descriptor-ring DMA engine. It is
a hardware **buffer-manager + queue** model, as one would expect from an NPU-style
packet processor:

1. **Credit/quota check against the TM block.** A counter in U-Boot's private
   struct (`0x47f5a640`, fields at `+0x48/+0x4c/+0x50/+0x54/+0x58`) is
   replenished from **`0x92350000 + 0x68`** (the `tm@92340000` block). If credit
   is short the packet is dropped and a counter incremented.
2. **Allocate a buffer from the hardware pool** — a helper returns an index that
   is range-checked `< 2048`, then `lsl #11` converts it to a byte offset, i.e.
   **2 KiB buffers**.
3. **Write a descriptor** — `str r3, [lr, ip, lsl #4]` plus
   `stmib r2, {r3, ip, lr}`, so descriptors are **16 bytes**; the observed words
   are `0x80`, `0x10000`, `0x1000000`, `0x2`.
4. **Doorbell/enqueue** (`0x47f300d4`).

So a Linux driver must model: buffer pool alloc/free, 16-byte descriptors,
per-port TM credits, and the enqueue doorbell — rather than `dma_alloc` ring
buffers. That is a meaningful amount of work, but the shape is now known.

## Next

1. Decode the buffer-pool allocator (`0x47f2f92c`) and the free path — that is
   the remaining unknown for TX.
2. Decode `recv` (`0x47f2feb4`) for the RX queue/poll model.
3. Then write `zx279128-eth` using the MDIO/PHY layer that already works.

## Datapath specification (decoded)

### Blocks

| block | base | fields seen |
|---|---|---|
| Datapath reset | `0x92000000` | `+0x08` bitmask; clear bits, delay 10 us, write `0xffffffff` to release |
| MAC (per port) | `0x92200000` + port*`0x40000` | `+0x070`, `+0x0b4`, `+0x0e0`, `+0xb00`, `+0xd00`, `+0xd30` |
| Buffer manager (BM) | `0x92348000` | `+0x00` enable, `+0x0c` alloc index, `+0x10` free, `+0x14` request/busy, `+0xdc[8:3]` free count |
| TM config | `0x92340000` | `+0x04` = 16, **`+0xf0` = descriptor ring base (`0x41a00000`)** |
| TM queues | `0x92350000` | `+0x68` TX credit, `+0x11c` RX pending count (16-bit) |
| misc init | `0x92040000`, `0x923a0000` | `+0x18` &= ~3, `+0x1c` = 15; `+0xe0` = 17 |
| Link status | `0x921d9000` | `+0x68` — **unconfirmed**, reads 0 while link is up |
| Packet buffers | **`0x41000000`** (DDR) | 2 KiB per buffer, 16-byte header, 2048 entries |
| Descriptor ring | **`0x41a00000`** (DDR) | 1024 entries x 16 bytes |

### Hardware check of ring base

```
tmbase +004=00000010 +0f0=41a00000
```

Both read back exactly what U-Boot programs, confirming the TM config base and
the ring base. Both DDR windows are reserved in the DT and confirmed at boot:

```
OF: reserved mem: 0x41000000..0x413fffff (4096 KiB) eth-buffers@41000000
OF: reserved mem: 0x41a00000..0x41a0ffff (64 KiB)   eth-ring@41a00000
```

### Buffer pool

`0x47f2f92c` is the allocator:

```
write 1 -> BM+0x14          ; request a buffer
poll BM+0x14 until 0        ; up to 4 tries
idx = BM+0x0c               ; 16-bit; negative => exhausted (returns -11)
```

`0x47f2f99c` is the matching free:

```
if (sw_credit == 0)                  ; software mirror of free slots
        sw_credit = (BM+0xdc >> 3) & 0x3f    ; refill, 6-bit count, 4 tries
sw_credit--
write idx -> BM+0x10        ; return the buffer to the pool
```

So the complete BM API is: `+0x00` enable, `+0x0c` allocated index,
`+0x10` free (write index), `+0x14` request/busy, `+0xdc` bits `[8:3]` free-slot
count.

Index → memory: **`0x41000000 + (idx << 11) + 16`** — i.e. 2 KiB buffers in a
reserved DDR window, payload starting 16 bytes in. A Linux driver must therefore
**reserve `0x41000000`** (memory-region / `no-map`) rather than allocate its own
DMA buffers.

### TX sequence (`send`, `0x47f301f8`)

1. Check/refresh TX credit against `TM+0x68`; drop and bump a counter if short.
2. Allocate a buffer index from the BM (above).
3. `memcpy` the frame to `0x41000000 + (idx<<11) + 16`.
4. Fill the **16-byte descriptor** with bit-packed fields:
   - buffer index bits `[6:0]` → desc byte `+7`, bit offset 1 (`bfi r3, r6, #1, #7`)
   - buffer index bits `[14:7]` → desc byte `+8`
   - frame length (14-bit) → halfword `+12`, bit offset 2, and also into `+8`
     at bit offset 9
   - constants observed elsewhere in the descriptor: `0x80`, `0x10000`,
     `0x1000000`, `0x2`
5. Doorbell/enqueue (`0x47f300d4`).

### RX sequence (`recv`, `0x47f2feb4`)

Polls **`TM+0x11c`** for a 16-bit pending count; zero means no packet. Then walks
a **descriptor ring of 1024 entries x 16 bytes**:

```
i    = ring_index                       ; kept in U-Boot's private struct
desc = ring_base + (i << 4)             ; 16-byte descriptors
ring_index = (i + 1) % 1024             ; wraps at 1024
cache-invalidate desc..desc+16
idx  = (desc[7] >> 1) | (desc[8] << 7)  ; inverse of the TX packing
if (idx >= 2048) -> error
payload = 0x41000000 + (idx << 11) + 16
len     = desc[12..13] >> 2             ; 14-bit
... hand packet up, then free idx back to the BM (BM+0x10)
```

Queue index 7 is used with an 8-byte stride (`lsl r6, #3`) when addressing the
per-queue registers.

## Buffer pool reserved in DT (done)

The pool is 2048 buffers x 2 KiB = 4 MiB at `0x41000000`, so the DT now carries:

```dts
reserved-memory {
        eth_bufs: eth-buffers@41000000 {
                reg = <0x41000000 0x400000>;
                no-map;
        };
};
```

Confirmed on the board:

```
OF: reserved mem: 0x41000000..0x413fffff (4096 KiB) nomap non-reusable eth-buffers@41000000
Memory: 116640K/131072K available (... 14432K reserved ...)     <- was 10336K, exactly +4 MiB
```

## Next

The datapath spec above is complete (MAC, BM alloc/free, TM credits + RX count,
buffer addressing, descriptor packing, RX ring geometry). What remains is
writing `zx279128-eth`:

1. netdev + NAPI poll driven by `TM+0x11c`.
2. TX: credit check -> BM alloc -> copy to `0x41000000+(idx<<11)+16` -> pack
   descriptor -> doorbell.
3. RX: walk the 1024-entry ring, unpack idx/len, hand up an skb, free idx to
   `BM+0x10`.
4. Link handling via the existing MDIO/PHY layer (`ethernet-phy@10..13`), and
   re-confirm which register really carries link state (`0x921d9000+0x68`
   read 0 while U-Boot reported 1000M full-duplex).

### Hardware check of BM/TM

Dumped live from the board (same probe-time aid as the MAC check):

```
mac0 +070=00300002 +0b4=00004000 +0e0=00000000 +b00=0000ff01
bm   +000=00000001 +00c=00000000 +014=00000000
tm   +068=000006f8 +11c=00000000
link +068=00000000
```

- `bm+0x00 = 1` — the buffer manager is **enabled**, matching the tiny U-Boot
  helper that writes 1 to `0x92348000`. Confirms the BM base.
- `bm+0x14 = 0` — idle, consistent with the "write 1, poll until 0" protocol.
- `tm+0x68 = 0x6f8` (1784) — a live, non-zero **credit count**, exactly what the
  TX path decrements. Confirms the TM base and the credit interpretation.
- `tm+0x11c = 0` — no RX pending, correct with no traffic arriving.
- `link+0x68 = 0` — **does not** match U-Boot's `mac 0 phy status changed:
  1000M full-duplex`, so either that register is not the link word, or the PHY
  was reset by phylib after U-Boot. Needs revisiting; treat `0x921d9000` as
  unconfirmed.


## Driver: `zx279128-eth`

`files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c`
(`CONFIG_ZX279128_ETH`, compatible `zte,zx279128s-eth`), DT node
`ethernet@92200000` with `phy-handle = <&phy0>` and
`memory-region = <&eth_bufs>, <&eth_ring>`.

Design notes:

- It deliberately **does not re-run the vendor global datapath init**. The
  bootloader has already initialised BM/TM (its TFTP works), so the driver
  attaches to the running configuration; re-initialising is a riskier separate
  step.
- TX: credit check (`TM+0x68`) -> `zx_bm_alloc()` -> `memcpy_toio` to
  `0x41000000+(idx<<11)+16` -> `zx_desc_pack()` -> `wmb()` -> doorbell
  `TM+0x64 = 1`.
- RX (NAPI): poll `TM+0x11c`, walk the 1024-entry ring, `zx_desc_unpack()`,
  copy into an skb, then `zx_bm_free()` -> `BM+0x10`.

### Working

```
zx279128-eth 92200000.ethernet: bm=92348000 tmc=92340000 tmq=92350000 ring_base=41a00000 cfg=00000010
zx279128-eth 92200000.ethernet eth0: Link is Up - 1Gbps/Full - flow control off
```

The driver probes, reads the ring base back from hardware (`0x41a00000`,
matching the decode), registers `eth0`, and phylib negotiates 1 Gbps full duplex
through the MDIO driver. That also answers an earlier open question: link state
comes from the PHY over MDIO, so the unconfirmed `0x921d9000+0x68` register is
not needed.

### Blocking issue: pppoe notifier crash

Bringing the interface up under `netifd` panics **inside the pppoe module**, not
in this driver:

```
Unable to handle kernel NULL pointer dereference at virtual address 00000680
PC is at pppoe_device_event+0x3c/0x200
LR is at raw_notifier_call_chain+0x34/0x68
Comm: netifd
```

`0x680` is consistent with `net_generic()` dereferencing a NULL `struct net`,
i.e. `dev_net(dev)` returning NULL in the notifier. Moving `of_phy_connect()`
out of `probe()` into `ndo_open()` (the conventional pattern, since connecting a
PHY to an unregistered netdev leaves it half-initialised) got the driver much
further — link up, allmulticast, promiscuous — but the panic still occurs when
netifd configures the interface.

Next step is to validate TX/RX in isolation by booting `init=/bin/sh` (no
kmodloader, no netifd, no pppoe) and configuring `eth0` by hand, which separates
the datapath from this userspace/module interaction.


## TX verified on the wire (round 26)

Testing under `netifd` is blocked by the pppoe crash, so validation was done by
booting **`init=/bin/sh`** (no kmodloader, no netifd, no pppoe) and configuring
the interface by hand. No panic in that environment.

Two real driver bugs were found and fixed by following the counters:

1. **TX credit polarity.** `TM+0x68` is not "credits available" — the vendor
   keeps a software counter and *subtracts* this register from it, so it reports
   credits *consumed*. Gating on it being non-zero rejected every frame
   (`tx_fifo_errors` climbed, `tx_packets` stayed 0). Replaced with the vendor's
   outstanding-frame accounting.
2. **Buffer-manager valid bit.** The allocator returns the index only when
   `BM+0x0c` reads back **negative** (bit31 = valid), taking the low 16 bits:
   ```
   ldr r0, [r1, #12] ; cmp r0, #0 ; bge -> FAILURE ; uxth r0, r0
   ```
   The test was inverted, so every allocation failed — `tx_dropped` incremented
   exactly once per ARP probe while `tx_packets` stayed 0.

With both fixed, frames reach the wire. Captured on the host:

```
ea:dd:45:a8:40:2e > ff:ff:ff:ff:ff:ff, ARP Request who-has 192.168.1.100 tell 192.168.1.1
00:e0:4c:12:59:90 > ea:dd:45:a8:40:2e, ARP Reply  192.168.1.100 is-at 00:e0:4c:12:59:90
```

and the device counts `tx_bytes=852 tx_packets=12`. So BM alloc -> buffer copy ->
descriptor packing -> doorbell is a working transmit path.

### RX still not receiving

The host's ARP replies arrive at the board but `rx_packets` stays 0. Most likely
cause: the **RX ring base differs from the TX ring base**. This driver programs
its ring pointer from `TMC+0xf0` (`0x41a00000`), but U-Boot's `recv` takes the
ring address from its own private struct (`0x47f5a640`/`0x47f5a648`), which is
not necessarily the same ring. RX may also require buffers to be pre-posted to
the hardware before it will deliver frames.

Next: decode where `recv` gets its ring base and whether RX buffers must be
posted, then re-test.


## RX debugging (round 27)

Three concrete findings, two of them fixed:

### 1. NAPI was never scheduled (fixed)

The driver called `napi_enable()` but nothing ever called `napi_schedule()` —
there is no RX interrupt decoded and there was no timer, so `zx_eth_poll()` never
ran. U-Boot simply polls `recv()` in a loop. Added a 1 ms timer that schedules
NAPI while the interface is up; replace with a real IRQ once the
`pon@92000000` interrupt (`SPI 34` in the stock DTS) is understood.

### 2. U-Boot leaves every port DISABLED (fixed)

`halt()` (`0x47f30834`) clears **bit0 of MAC+0x00** per port:

```
addr = 0x92200000 + (port << 18)
[addr] &= ~1
```

and U-Boot runs `halt()` after *every* TFTP transfer, so Linux inherits disabled
ports. Confirmed on hardware — the register read back `0x00bb6002` (bit0 clear)
and setting it gave `0x00bb6003`:

```
zx279128-eth eth0: port enable: MAC+0x00 00bb6002 -> 00bb6003
```

This explains why TX worked while RX did not: transmit goes through the BM/TM
doorbell, but reception needs the port enabled.

### 3. Still no RX — CPU delivery not configured

Even with the port enabled and NAPI polling, `TM+0x11c` never becomes non-zero,
so the hardware is not queuing frames to us. Setting the interface MAC to the
vendor default made no difference, so this is not simple unicast filtering.

The remaining suspect is that this is a **switch/NPU datapath**: incoming frames
are classified by the NPP/PP and only reach the CPU queue if a rule says so.
The driver deliberately skips the vendor's global init, so those rules are
missing (or were torn down). Next: decode the per-port init `0x47f305e4` and the
classification setup (`0x47f2fb9c`, `0x47f2fcec`, `0x47f303f0`) that U-Boot runs
before its first successful receive, and apply the minimum needed to steer
frames to the CPU queue.


## RX debugging (round 28)

### PP steering was already enabled — not the missing piece

The vendor init chain writes `0x9238c000+0x80/0x88/0xcc` (inside
`pp@92380000`). Applying those from the driver changed nothing, because the
bootloader had already done it:

```
pp before: +80=0000301a +88=00000000 +cc=00000001
pp after : +80=0000301a +88=00000000 +cc=00000001
```

`+0xcc` already reads 1, and `+0x80` **ignores writes** (wrote `0x309a`, read
back `0x301a`). So CPU steering is enabled and is not what blocks RX.

### Cross-check: port -> PHY table

The per-port init (`0x47f305e4`) is mostly PHY setup over MDIO (vendor registers
26 and 30), indexed through a port->PHY-address table at `0x47f4b63c`:

```
[10, 11, 12, 13, 0, 255, 255, 255]
```

This independently confirms the MDIO scan result (PHYs at addresses 10-13).

### Empirical scan for the RX indication

Rather than guess further, the driver now diffs the whole TM window every 2 s.
With traffic being sent at the board, these move:

| register | behaviour |
|---|---|
| `TM+0x100` | slow +1 counter |
| `TM+0x158` | +2 |
| `TM+0x160` | two 16-bit halves incrementing **together** (`0x03000300` -> `0x04000400`) — looks like producer/consumer indices that stay equal |
| `TM+0x170` | slow +1 |
| `TM+0x180` | +0x200 steps |
| `TM+0x1a0` | slow counter |
| `TM+0x1c4`, `TM+0x1cc` | changing |

**`TM+0x11c` never appears** — it genuinely stays 0.

Interpretation: the deltas are 1-2 per interval regardless of how many frames are
injected (~20 pings produced no matching jump), so these are housekeeping
counters, not per-packet RX counts. Combined with the producer/consumer pair at
`+0x160` staying equal, the evidence says **frames are not entering the CPU queue
at all** — they are dropped before the TM, i.e. in the MAC/port RX path or by
classification, despite `MAC+0x00` bit0 being set.

Next experiment: inject an exact number of frames (e.g. 100) and look for a
register that moves by exactly that amount, to separate real packet counters from
housekeeping; and dump the MAC per-port window (`0x92200000`) the same way to see
whether the port counts received frames at all.


## RX debugging (round 29) — hardware RX proven working; driver cursor wrong

### TM+0x170 is the RX indication, but it is a GAUGE

Injecting exact frame counts (raw AF_PACKET bursts, verified by tcpdump) moved
`TM+0x170` and `TM+0x1a0` by exactly the injected count (+100, +80). But it is
NOT monotonic: with nobody consuming, the hardware eventually drains stale
frames and the register DROPS (observed 249 -> 53). The driver must treat
deltas as pending work and resync on negative jumps (implemented).

`TM+0x11c` (what U-Boot's recv reads) stays 0 in our environment - wrong queue
for this configuration.

### Burst frames located in memory — the decisive observation

Searching the pool and ring for the distinctive burst payload:

```
zx-scan: burst payload in buf 64..69 (consecutive)
zx-scan: ring[762..765] len=64 buf=0
zx-scan: ring[766] len=64 buf=64
zx-scan: ring[767] len=64 buf=66
```

Conclusions:

- **The hardware receives frames end-to-end**: pool buffers are allocated
  sequentially (64..69) and frames are DMA'd into them at `+16` header offset.
- **Descriptors are written into the ring** — around slot 762, i.e. wherever
  the hardware's write pointer happens to be, NOT slot 0 where the driver's
  cursor started. That is why the poll loop returned nothing even when it ran.
- The alternating `buf=0 / buf=64 / buf=66` pattern suggests **RX descriptors
  may be 32 bytes** (my 16-byte decode reads valid data only in alternate
  slots), or the packing differs from TX. Needs one more look.

### Next (concrete)

Track the ring by CONTENT, not by a pointer register: keep a shadow copy of the
ring, diff it in poll to find newly-written descriptors, process those slots and
resync the cursor there. Verify the 32-byte-descriptor hypothesis by dumping
raw ring words around slot 762 after a burst.


## RX WORKING (round 29 continued)

### Root cause of the stall

The RX descriptor decode was correct all along. Raw ring bytes after a burst:

```
ring[766] buf=64: 200001ca 80080000 20008000 00000100
                           ^^ byte7 0x80>>1 = 64          ^^ 0x100>>2 = 64 bytes
ring[767] buf=65: 200001ca 82080000 20008000 00000100   (0x82>>1 = 65)
```

16-byte descriptors, `idx` and `len` exactly as decoded. The bug was purely
**cursor position**: the hardware writes wherever its own pointer sits (slot
~762) while the driver started at slot 0, so it only ever read stale zeros.

### Fix

- Zero the ring in `ndo_open()`, so any non-zero descriptor is new.
- In `poll()`, scan forward from the cursor (wrapping) for the next non-zero
  descriptor, consume it, and zero it. The writer does not necessarily continue
  from our cursor and can jump, so a fixed cursor stalls after the first run.

### Verified

Injecting exactly 30 raw frames of 64 bytes:

```
eth0: rx_bytes=1920  rx_packets=30  rx_errors=0
                     ^^ 30/30           ^^ 1920 = 30 x 64 exactly
```

And with real traffic the ARP reply is received and processed by the stack:

```
ip neigh -> 192.168.1.100 dev eth0 lladdr 00:e0:4c:12:59:90 STALE
```

So the datapath now works in **both directions**: TX frames reach the wire and
RX frames reach the network stack, all built from bootloader RE.

### Remaining

`ping` still does not complete: ARP resolves, but the unicast ICMP echo replies
are not delivered to the CPU queue (RX counter does not advance for them, and
they are not counted as errors or drops). Likely the NPU forwards unicast
traffic in hardware rather than to the CPU port, so a classification/forwarding
rule is needed to punt unicast destined for our MAC to the CPU. Broadcast and
ARP clearly do reach us.


## Round 30: two driver bugs fixed, and the port-mode discovery

### Bug: TX and RX collided on the ring

`xmit` wrote its descriptor at `ring + ring_idx*16`, reusing the **RX cursor**.
While RX never ran, `ring_idx` stayed 0 and TX worked by accident; once RX began
advancing the cursor, transmits scribbled over RX descriptors. TX now owns a
dedicated slot (`TX_DESC_SLOT = 0`) and the RX scan skips it.

### Bug: zeroing descriptors destroyed hardware control fields

Descriptor words 0 and 2 are constant control fields (`0x200001ca`,
`0x20008000`) and `zx_desc_pack()` only read-modify-writes idx/len. The
round-29 `memset_io(ring, 0, ...)` wiped those templates. Consumption now clears
**only the length halfword**, and "new descriptor" means non-zero length.

### The port-mode bit (measured, not guessed)

`MAC+0x00` bit0 is **not** an enable. A/B tested on port 0:

| bit0 | TX egress (host tcpdump) | RX to CPU |
|---|---|---|
| 0 (as bootloader leaves it) | ✅ ARP requests seen on the wire | ❌ nothing |
| 1 (driver sets it) | ❌ nothing on the wire | ✅ 20/20 and 25/25 frames |

So the bit switches the port between "drive the wire" and "feed the CPU", and
`halt()` clearing it is what left RX dead in earlier rounds.

Port 4 (`0x92300000`) was tested as a possible dedicated CPU port: it reads
`0x00000000`, so it is not one.

Crucially, in mode 1 the **wire -> CPU direction still works**, so the port is
not detached from the PHY. That means our transmits are being steered somewhere
other than the wire — most likely the TX descriptor needs a **destination-port
field**, encoded in the control words we currently inherit from whatever
template sat in the ring slot.

### Next

Decode the descriptor control words (`0x200001ca` / `0x20008000`) to find the
source/destination port field, set it explicitly for TX, and re-test with
bit0=1 so both directions work simultaneously. U-Boot's `send` path
(`0x47f300d4`, which writes `0x80`, `0x10000`, `0x1000000`, `0x2` into the
descriptor) is the reference for those fields.


## Round 31: TX and RX working at the same time

### The fix: write the vendor TX descriptor template explicitly

The driver had been *inheriting* whatever descriptor template happened to sit in
the ring slot. Writing the vendor's template from U-Boot's send tail
(`0x47f302a0`) instead:

```
w0 = 0x00000080   w1 = 0x00010000   w2 = 0x01000000   w3 = 0x00000002
```

immediately resolved the round-30 dilemma. With the port in CPU mode
(`MAC+0x00` bit0 = 1) **both directions now work at once**:

```
host tcpdump: ARP, Request who-has 192.168.1.100 tell 192.168.1.1   <- device TX on the wire
              ARP, Reply  192.168.1.100 is-at 00:e0:4c:12:59:90
device:       rx_bytes=1880 rx_packets=20   tx_packets=11
ip neigh:     192.168.1.100 dev eth0 lladdr 00:e0:4c:12:59:90 STALE
```

So the earlier "TX xor RX" behaviour was not a hardware limitation of the mode
bit at all — it was a stale TX descriptor template.

### Tried and rejected: byte 11 port field

U-Boot also does `bfi r3, #16, #1, #7; strb r3, [r4, #11]` (byte11 = `0x20`),
and RX descriptors indeed show `0x20` there. Writing that on TX made things
**strictly worse** — even broadcast stopped egressing — so the field means
something different on the transmit path. Reverted; do not repeat.

### Remaining: unicast TX does not egress

Broadcast frames (ARP requests) reach the wire; unicast frames (ICMP echo to a
resolved neighbour) do not appear on the wire at all, even though `tx_packets`
increments. So `ping` still fails despite ARP resolving in both directions.

That asymmetry points at a destination/forwarding field in the descriptor (or an
L2 FDB lookup) that is fine for flooded traffic but wrong for unicast. Next:
diff a broadcast vs unicast TX descriptor as actually written (dump all four
words for each), and compare against what U-Boot builds for a unicast TFTP
transfer.


## Round 32: TX truncation identified

### The real symptom is not "unicast" — it is truncation

Pinging the broadcast address put ICMP on the wire, and tcpdump showed exactly
what is wrong:

```
IP [total length 84 > length 46] (invalid) 192.168.1.1 > 192.168.1.255: ICMP echo request
```

The IP header says 84 bytes but the frame carried only **46 bytes of payload**,
i.e. every transmit is cut to the 60-byte Ethernet minimum. That reframes the
round-31 "unicast does not egress" conclusion:

- ARP (42 B) is *below* the minimum anyway, so padding makes it valid and it
  works end to end.
- ICMP (98 B) is truncated to 60 B and discarded by the receiver as malformed.

So TX egress works for every frame; the **length is not reaching the hardware**.

### Ports 1 and 4 are not usable as a CPU port

Both read `0x00000000` (vs `0x00bb6002` for port 0), i.e. unconfigured. Setting
bit0 on either gives no RX. CPU mode must be set on port 0.

### RX buffer header is empty

The 16 bytes preceding the RX payload read back all zero, so the hardware does
not stage a length there and TX cannot copy that format:

```
rxhdr buf=0 len=64: 00000000 00000000 00000000 00000000
```

Also noted: some consumed RX descriptors decode `buf=0` although the payload
search earlier found frames in buffers 64-69 — the RX descriptor cursor is
picking up stale entries some of the time. Worth fixing alongside.

### Next

Find where the hardware takes the TX length from. The descriptor length fields
(`halfword+12` bits 2-15 and `word+8` bits 9-22) are written exactly as U-Boot
does and are confirmed correct on the RX side, so either TX uses a different
field, or the length must also be programmed somewhere in the TM/BM before the
doorbell. Compare a 42-byte and a 98-byte transmit by dumping all four
descriptor words immediately before ringing the doorbell.


## Round 33: length is correct — the buffer allocator is the problem

### TX descriptor length fields are provably right

Dumping the descriptor immediately before the doorbell:

```
txdesc len=90 idx=0 raw=80000000 freecnt=50000111: 00000080 00010000 0100b400 0000016a
txdesc len=70 idx=0 raw=80000000 freecnt=50000111: 00000080 00010000 01008c00 0000011a
```

- `w2 = 0x0100b400` -> bits 9-22 = `0x5a` = **90** ✓
- `w3 = 0x0000016a` -> bits 2-15 = `0x5a` = **90** ✓

Both length encodings match the frame exactly, and they track frame size
(90/86/70). So the descriptor is not where the truncation comes from.

### The buffer allocator never actually allocates

Every transmit shows:

```
raw = 0x80000000     -> bit31 valid, index 0, every single time
freecnt = 0x50000111 -> never changes
```

So `BM+0x14 = 1` is not triggering a real allocation: the pool always reports
buffer 0 and the free counter is static. Every frame is therefore written into
buffer 0, and frames sent from buffer 0 come out truncated at the 60-byte
minimum.

By contrast the **hardware's own RX allocation works** — received frames land in
sequential buffers (64-69 observed), so the pool itself is functional; only our
request path is wrong.

### Tested and rejected: bypassing the pool

Using private, un-allocated indices (1024+) stopped egress **completely** —
not even truncated frames appear. So the hardware genuinely requires buffers
handed out by the pool; picking an index ourselves is not viable, and the fix
must be to the allocation protocol.

### Next

Re-derive the BM request sequence from U-Boot (`0x47f2f92c`) paying attention to
what else is written before `BM+0x14`: the vendor reads a software mirror at
`+0x10` of its private struct and refills it from `BM+0xdc` bits [8:3]; there may
be a per-queue or per-port selector register that must be set before the request,
which would explain a static `0x80000000` reply.


## Round 34: byte-6 hypothesis rejected; an invalid earlier test found

### Tried and rejected: byte 6 as "length in 8-byte units"

A hardware-written RX descriptor for a 64-byte frame carries `w1 = 0x80080000`,
i.e. byte6 = `0x08` = 64/8, while the vendor TX template leaves byte6 = `0x01`
(= 8 bytes) — which lines up suspiciously well with transmits truncated to the
Ethernet minimum. Setting byte6 from the real frame length changed nothing:

```
IP [total length 84 > length 46] (invalid) ... ICMP echo request
```

So byte6 is not the transmit length. Reverted.

### Correction: the round-32 "RX buffer header is empty" result was invalid

That test dumped the header of whatever buffer the RX descriptor named — and
those descriptors decoded `buf=0`, so it dumped **buffer 0**, not a buffer the
hardware had actually filled. The conclusion "the hardware does not stage a
length in the buffer header" is therefore **unproven**, not disproven, and the
hypothesis is back open.

### Confirmed real bug: RX descriptors frequently decode idx = 0

Both the round-32 and round-34 dumps show consumed RX descriptors reporting
`buf=0` even though injected frames demonstrably land in buffers 64-69. So the
RX cursor is picking up stale/unwritten slots a large fraction of the time,
which means some delivered frames carry the contents of buffer 0 rather than the
received frame. Packet *counts* were right, which is why this hid for so long.

This needs fixing before any further TX conclusions are drawn from RX-derived
evidence — the descriptor layout facts used to build the TX path came from
descriptors read this way.

### Next

1. Fix RX descriptor validity: require a plausible `idx`/`len` pair (and ideally
   an ownership bit) before consuming a slot, so `buf=0` entries are not treated
   as received frames.
2. Re-dump a genuine RX buffer header with that in place, and re-test whether the
   hardware stages a length there for TX.


## Round 35: RX descriptor ownership fixed

### Ownership bit found

Descriptors the hardware has genuinely written carry **`0x20` in w2 byte 3**
(`w2 = 0x20008000`); stale slots do not. Using that as the ownership test, plus
a sanity range on `len`, makes RX exact:

```
12 frames injected ->  rx_bytes=768  rx_packets=12  rx_errors=0
                                     ^^ 12/12        ^^ 768 = 12 x 64
```

Previously the same test produced 12 *errors* or silently consumed stale slots.

### `idx == 0` is legitimate

Rejecting `idx == 0` discarded every real frame (`rx_errors` matched the
injected count exactly), which proves the hardware really is naming buffer 0.
That is consistent with the TX allocator always returning `raw = 0x80000000`
(index 0): **the pool is effectively operating with a single buffer** in this
configuration. So the round-34 worry that "frames carry buffer 0's contents
instead of the real frame" was unfounded — buffer 0 *is* the real frame buffer.

### Buffer header hypothesis now properly closed

Because `idx = 0` is the genuine RX buffer, the earlier dump *was* of a real
received frame's buffer, and it reads all zeros:

```
rxhdr buf=0 len=64: 00000000 00000000 00000000 00000000
```

So the hardware does **not** stage a length in the 16-byte buffer header. The
round-32 conclusion stands, now on sound evidence rather than an accidental
read of the wrong buffer.

### Where TX truncation stands

Ruled out so far: descriptor length fields (verified correct for 70/86/90-byte
frames), byte 6 as a length, the buffer header, and choosing our own buffer
index (stops egress entirely). Still open: the pool only ever yields buffer 0,
so TX and RX share it — a strong candidate for why transmits are clipped to the
60-byte minimum. Fixing the allocation request protocol so the pool hands out
distinct buffers is the next concrete step.


## Round 36: NPP enable ruled out; driver cleaned up

### Tried and rejected: running the vendor NPP enable

`0x47f308c4` writes all-ones to `0x921c0000 + 0x08` and `+0x0c`, then clears
`+0x48`. Performing that from `ndo_open()` is a **no-op** — the registers read
back unchanged:

```
npp before: +08=00000000 +0c=0003ffff +48=00000000
npp after : +08=00000000 +0c=0003ffff +48=00000000
```

So the packet processor is already enabled by the bootloader and this is not why
the buffer pool fails to cycle. The allocator still reports
`raw=80000000 freecnt=50000111` unchanged.

### Driver cleaned

Debug scaffolding (TX descriptor dumps, RX header dumps, the TM/MAC register
scanner) has been removed now that it has served its purpose; the findings are
recorded here instead. Re-verified after cleanup:

```
Link is Up - 1Gbps/Full
16 frames injected -> rx_bytes=1024 rx_packets=16 rx_errors=0   (1024 = 16 x 64)
```

### Current TX truncation status — everything ruled out so far

| candidate | verdict |
|---|---|
| descriptor length fields | correct (verified for 70/86/90-byte frames) |
| byte 6 as length-in-octets | no effect |
| 16-byte buffer header | hardware does not stage length there |
| choosing our own buffer index | stops egress entirely |
| NPP enable sequence | no-op, already enabled |
| separate CPU port (1 or 4) | those MACs are unconfigured |

Remaining lead: the buffer manager only ever yields buffer 0
(`BM+0x0c = 0x80000000`, `BM+0xdc` static), so TX and RX share a single buffer.
The vendor fills the pool somewhere in the init chain not yet located
(`0x47f30528`, `0x47f30878`, `0x47f308b0` are the unexplored calls inside
`0x47f308c4`).


## Round 37: vendor init is already applied by the bootloader

Two more pieces of the vendor init chain were located and tested from
`ndo_open()`. Both are **no-ops** — the hardware already holds the target values:

| vendor init | registers | result |
|---|---|---|
| `0x47f30528` queue/pool cfg | `0x921d4000` `+0x000/+0x004/+0x040/+0x044/+0x1c0`, queue enables at `0x921d428c` (map `0,1,2,3,4,-1,5,6`) | already `0x30000000 / 0x8800 / 0x11000000` before we write |
| `0x47f308c4` NPP enable | `0x921c0000 +0x08/+0x0c/+0x48` | reads back unchanged (`+0x0c = 0x0003ffff`) |

Also decoded: `0x47f30878` writes `0xffffffff` per port into a table and calls a
per-port helper; `0x47f308b0` writes `0x11` to `0x921cc000`.

**Conclusion: the bootloader leaves the whole datapath configured**, so
"missing init" is not the explanation for either the single-buffer pool or the
TX truncation. Re-running vendor init from Linux is a dead end; the difference
between our TX and U-Boot's must be in the per-frame sequence, not in setup.

### One difference from U-Boot worth pursuing

U-Boot explicitly **flushes the D-cache** twice per transmit before the doorbell:

```
bl 0x47f00eec  (buffer, buffer + len)   ; after memcpy of the frame
bl 0x47f00eec  (desc,   desc   + 16)    ; inside the enqueue, before TM+0x64 = 1
```

This driver instead maps the pool and ring with `ioremap_wc` and relies on
`wmb()`. That is normally sufficient for Normal-NC memory, but it is the one
remaining structural difference from the working vendor path, and it is cheap to
test by mapping the regions cached and using explicit cache maintenance.

Verified again after reverting the no-op writes:

```
Link is Up - 1Gbps/Full
14 frames injected -> rx_bytes=896 rx_packets=14 rx_errors=0   (896 = 14 x 64)
```


## Round 38: the datapath DDR memory map

Scanning the TM windows for values that look like DDR addresses revealed the
whole layout the hardware uses:

| register | value | meaning |
|---|---|---|
| `TMC+0x0e8` | `0x41800000` | (unidentified) |
| `TMC+0x0ec` | `0x41808000` | (unidentified) |
| `TMC+0x0f0` | `0x41a00000` | **RX descriptor ring** (hardware writes here) |
| `TMC+0x0f4` | `0x41000000` | **buffer pool base** (confirms the earlier decode) |
| `TMC+0x0f8` | `0x41400000` | (unidentified) |
| `TMQ+0x050` | `0x41b00000` | (unidentified queue region) |
| `TMQ+0x060` | `0x41c00000` | **TX ring base** — adjacent to `+0x64` doorbell and `+0x68` credit |

`TMC+0x4e8..0x4f8` mirror `+0x0e8..0x0f8`.

The DT reservation now covers the whole window rather than two guesses:

```
OF: reserved mem: 0x41000000..0x41ffffff (16384 KiB) nomap non-reusable eth-datapath@41000000
```

The driver now writes TX descriptors into the **TX** ring (`TMQ+0x60`) instead
of the RX ring, which is architecturally right regardless.

### Still truncated — what that now tells us

Frames continue to egress with correct content but a 60-byte length even with
descriptors in the proper TX ring. Since the hardware clearly *responds to our
doorbell* and transmits *our buffer 0 data*, it must be consuming a descriptor
that names buffer 0 with a small length — i.e. **it is not reading the
descriptor we write**, wherever we write it.

Rejected this round in addition: replicating the descriptor across the first 32
ring slots (in case the hardware reads at its own position) changed nothing.

### Next

Find how the hardware selects which TX descriptor to consume. Candidates:
a producer/consumer index register in the TM queue block (`TMQ+0x50` region is
still unidentified), or the doorbell value encoding a slot rather than the
constant `1`. Dump `TMQ+0x40..0x70` before and after a transmit to see which
index register moves.


## Round 39: the TX descriptor index register — and what it proves

Diffing `TMQ+0x40..0x70` immediately before and after the doorbell shows exactly
two registers move per transmit:

```
tx len=90  TMQ+0x68: 00000000 -> 00000001      (TX completion / credits consumed)
tx len=90  TMQ+0x6c: 06fa06fa -> 06fb06fb      (TX ring index, both 16-bit halves +1)
```

So **`TMQ+0x6c` is the TX ring index**. Note `0x6fa = 1786`, and
`1786 mod 1024 = 762` — the same slot where hardware-written RX descriptors were
found in round 29, which ties the two observations together.

### The decisive experiment

Writing our descriptor **at that index** (tried in both the TX ring `TMQ+0x60`
and the shared ring `TMC+0xf0`) makes the hardware **stop transmitting entirely**
— no frames on the wire at all. Writing to a fixed slot instead leaves it
transmitting a *stale* descriptor: correct buffer contents, minimum 60-byte
length.

That pair of outcomes is conclusive:

1. the hardware really does fetch its TX descriptor from `TMQ+0x6c`; and
2. **our descriptor content is invalid** — presented with it, the hardware
   discards the frame rather than sending it.

So the remaining defect is the TX descriptor *layout*, not its placement, not
the length encoding, not the buffer, and not any missing initialisation (all
previously eliminated). The vendor template
(`w0=0x80, w1=0x10000, w2=0x1000000, w3=2` plus idx/len packing) is evidently
incomplete or misordered for this path.

### Next

Capture a *real* TX descriptor: let the hardware transmit using its own stale
descriptor, then read the 16 bytes at the pre-doorbell index and compare against
what we construct. That gives a known-good TX descriptor to copy field for
field, the same way the RX layout was settled in round 29.

Driver left in the configuration that egresses (fixed slot). Verified after
revert: ARP on the wire, and RX exact.


## ✅ Round 40: ETHERNET WORKING — ping with 0% loss

### The final defect: descriptor byte 11

Capturing the descriptor sitting at the hardware's own TX index (the one it was
transmitting from) gave a known-good TX layout to diff against ours:

```
hw:   00000080 00010000 21005c00 000000ba     len = 0xba>>2 = 46  <- the truncation
ours: 00000080 00010000 0100b400 0000016a     len = 90
                        ^^
                  byte11 0x21 (hw) vs 0x01 (ours)
```

Byte 11 must be **`0x21`** — the template's `0x01` **OR** `0x20`. Round 31 tried a
bare `0x20`, which clobbered bit 0 and stopped transmits altogether; that made
the field look like a dead end when it was in fact the answer, just written
wrongly.

With byte 11 corrected **and** the descriptor written at the hardware's TX ring
index (`TMQ+0x6c`), transmission works:

```
64 bytes from 192.168.1.100: seq=1 ttl=64 time=5.927 ms
4 packets transmitted, 4 packets received, 0% packet loss

# and with 1028-byte packets, after removing all debug code:
10 packets transmitted, 10 packets received, 0% packet loss
round-trip min/avg/max = 2.702/5.077/23.590 ms
eth0: rx_bytes=10540 tx_bytes=11090
```

### Final TX sequence

```
1. outstanding-frame accounting against TM+0x68
2. idx = BM alloc  (write 1 -> BM+0x14, poll, read BM+0x0c; bit31 = valid)
3. memcpy frame -> 0x41000000 + (idx << 11) + 16
4. slot = TMQ+0x6c & 0xffff, modulo 1024
   desc = TX ring (TMQ+0x60) + slot * 16
   w0=0x00000080 w1=0x00010000 w2=0x01000000 w3=0x00000002
   pack idx (byte7 bits1-7, byte8) and len (halfword+12 bits2-15, word+8 bits9-22)
   byte11 |= 0x20      -> 0x21
5. wmb(), then doorbell TMQ+0x64 = 1
```

### Final RX sequence

```
NAPI polled from a 1 ms timer (no RX IRQ decoded yet)
scan the RX ring (TMC+0xf0) forward from the cursor for a slot whose
  w2 byte3 == 0x20 (ownership) and whose length field is non-zero
unpack idx/len, copy from 0x41000000 + (idx << 11) + 16 into an skb,
clear the length halfword to mark consumed, free idx -> BM+0x10
```


## Round 41: the driver needs its own datapath init for flash boots

Flashing the Ethernet-capable kernel and booting **from NAND with no TFTP** shows
a limitation that every earlier test had hidden:

```
zx279128-eth eth0: port mode: MAC+0x00 00000000 -> 00000001
zx279128-eth eth0: Link is Down
```

`MAC+0x00` reads **`0x00000000`**, not the `0x00bb6002` seen in every previous
test. The reason is simple in hindsight: all Ethernet testing so far booted the
kernel **over TFTP**, which makes U-Boot initialise the datapath first. On a
plain flash boot U-Boot never touches Ethernet, so the MAC, PHY and datapath are
left unconfigured and there is no link.

This driver deliberately attaches to the bootloader's configuration rather than
re-running the vendor init (rounds 36-37 showed that init is a no-op *when
U-Boot has already run it*). That choice is fine for bench testing over TFTP but
**not sufficient for a production image**: the driver must perform the full
bring-up itself.

What that means concretely — the driver has to do what U-Boot's `eth_init`
(`0x47f2fde4`) does before any traffic is possible:

1. datapath reset via `0x92000008` (clear bits, 10 us, write `0xffffffff`)
2. global datapath init (`0x47f2f7a8`): `0x92040000+0x18 &= ~3`, `+0x1c = 15`
3. the BM/TM/queue configuration that rounds 36-37 found already applied after a
   TFTP boot (`0x921d4000` pool base/size, queue enables at `0x921d428c`,
   NPP `0x921c0000`, `0x923a0000+0xe0 = 17`)
4. per-port init (`0x47f305e4`): PHY setup over MDIO (vendor registers 26 and 30)
   and the MAC register writes at `+0x070/+0x0b4/+0x0e0/+0xb00/+0xd00/+0xd30`

All of those register values are already documented above — they were recorded
while proving they were no-ops after a TFTP boot. They now need to be *applied*
unconditionally at probe.

### Also observed

This flash boot reached `procd: - early -` and then stopped responding on the
console, with **no** SQUASHFS errors. Needs separate investigation; the previous
flash boot to a shell (round 18) used a kernel without the Ethernet driver, so
the new probe path is the prime suspect - most likely the NAPI poll timer or the
PHY connect running against an uninitialised MAC.


## Round 42: driver self-initialises; boot stall fixed

### Datapath bring-up implemented

`zx_eth_datapath_init()` now performs the vendor sequence when the bootloader
has not (detected by `MAC+0x00` having no high bits set):

1. reset `0x92000008` (clear, 10 us, `0xffffffff`)
2. global `0x92040000`: `+0x18 &= ~3`, `+0x1c = 15`
3. NPP `0x921c0000`: `+0x08`/`+0x0c` all-ones, `+0x48 = 0`
4. queue/pool `0x921d4000`: enables at `+0x28c`, pool base/size, `+0x1c0`
5. `0x923a0000 + 0xe0 = 17`
6. per-port MAC `+0x070/+0x0b4/+0x0e0/+0xb00/+0xd00/+0xd30`

Confirmed running on a pure flash boot:

```
zx279128-eth 92200000.ethernet: datapath not initialised by bootloader, doing it
```

### Ring-base guard earned its place

After self-init, `TMC+0xf0` reads `0x50009000` — **not** a DDR address. The
fallback to the known constants kicked in correctly:

```
rx ring=41a00000 tx ring=41c00000   (ring_base register read 0x50009000)
```

Without that guard the driver would have `ioremap()`ed nonsense.

### Boot stall fixed: the RX scan was starving the system

The RX poll scanned all 1024 ring slots every 1 ms — ~1024 uncached reads per
millisecond. On a flash boot (where the ring never becomes valid) that was
enough to stall userspace at `procd: - early -`. The scan is now bounded to a
64-slot window per poll, advancing so the whole ring is still swept. Result:

```
procd: - early -   procd: - ubus -   procd: - init -
zx279128-eth eth0: entered allmulticast mode / promiscuous mode
```

i.e. the full OpenWrt boot completes and **netifd now manages eth0** — the
interface is configured rather than the boot hanging.

### Remaining blocker: pppoe notifier

Configuring the interface still panics inside the **pppoe module**:

```
Unable to handle kernel NULL pointer dereference at virtual address 00000680
PC is at pppoe_device_event+0x3c/0x200      Comm: netifd
```

`pppoe_pernet(dev_net(dev))` returns NULL, i.e. pppoe's per-netns data is not
available when its notifier runs. It fires on `NETDEV_CHANGEADDR`, which netifd
triggers when it sets the MAC. Nothing in this driver is on that path.

Practical fix for a bring-up image: build the rootfs **without** `kmod-pppoe`
(and the ppp stack), which is not needed for basic operation. That is a rootfs
rebuild rather than a driver change.


## Round 43: full OpenWrt boots from NAND with a managed eth0

### pppoe removed -> no more panic

The ppp/pppoe modules were dropped from the rootfs staging tree
(`etc/modules.d/ppp`, `etc/modules.d/pppoe`, and the four `.ko` files) and the
squashfs rebuilt with the same options OpenWrt uses (xz, 256 KiB blocks,
**`-Xbcj arm`** - omitting the BCJ filter made the image 97 KiB larger and is
worth remembering). The netifd panic is gone.

### The milestone

A pure flash boot - no TFTP anywhere - now reaches a shell with the interface
fully managed:

```
zx279128-eth eth0: datapath not initialised by bootloader, doing it
zx279128-eth eth0: Link is Up - 1Gbps/Full - flow control off
procd: - init -
root@OpenWrt:~# ip addr show eth0
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 ... master br-lan state UP
root@OpenWrt:~# ip addr show br-lan
    inet 192.168.1.1/24 brd 192.168.1.255 scope global br-lan
```

So the self-init brings the PHY up to 1 Gbps with no bootloader help, and
netifd enslaves eth0 into `br-lan` normally.

### Buffer pool must be populated after reset

Initially every transmit was dropped (`br-lan tx=14` vs `eth0 tx_packets=0,
tx_dropped=16, tx_fifo_errors=0`) — i.e. `zx_bm_alloc()` failing. After our reset
the pool is empty, so the driver now hands every buffer to the manager during
init (write each index to `BM+0x10`, then `BM+0x00 = 1`). TX then works:

```
eth0: tx_bytes=1812 tx_packets=16 tx_dropped=0
```

### Still open: RX on a flash boot, and TX not reaching the wire

`rx_packets` stays 0 after a flash boot, and a host capture shows the device's
ARP requests **do not appear on the wire** either — even though `tx_packets`
increments and nothing is dropped. Over a TFTP boot both directions work
(round 40, ping 0% loss), so the difference is still in what the bootloader
configures versus what `zx_eth_datapath_init()` reproduces.

Programming the DDR pointers explicitly (`TMC+0xe8/0xec/0xf0/0xf4/0xf8`,
`TMQ+0x50/0x60`, `TMC+0x04 = 16`) was added this round and did not change it.

Next: dump the full TM/BM/MAC register sets after a working TFTP boot and after a
flash boot, and diff them. Everything needed for that already exists in the
driver's debug history; the diff will name the missing register directly instead
of another hypothesis.


## Round 44: register diffing found the missing MAC control word

Dumping the same register digest at `ndo_open()` on a **working TFTP boot** and a
**failing flash boot** named the difference immediately:

```
          TFTP (works)   FLASH (broken)
mac +00   00bb6003       00000001      <-- 0x00bb6002 never programmed
bm  +dc   50000111       00000111
tmq +6c   06fa06fa       00000000      (ring index, not configuration)
```

`MAC+0x00` is the main control word (speed/duplex/enable). The init wrote
`+0x070/+0x0b4/+0x0e0/+0xb00/+0xd00/+0xd30` but never `+0x00`, so on a flash boot
the MAC was left unconfigured apart from the enable bit our `ndo_open()` sets.

Adding `writel(0x00bb6002, mac + 0x000)` to `zx_eth_datapath_init()` makes the
flash boot match the working one exactly:

```
zx279128-eth eth0: DIG mac 00bb6003 00300002 00004000 00000000 0000ff01 ...
zx279128-eth eth0: Link is Up - 1Gbps/Full - flow control off
```

TX on a flash boot now allocates and transmits (`tx_packets=16, tx_dropped=0`).

### One difference left

After the fix the two digests are identical except:

```
bm +0xdc:  0x50000111 (TFTP)  vs  0x00000111 (flash)
```

The low bits agree — `(0x111 >> 3) & 0x3f = 34` free slots in both — so only the
**top nibble `0x5` (bits 28 and 30)** is missing. Those look like pool/RX status
flags rather than a value we can simply write, and RX is still dead on a flash
boot while TX works.

Note also that 34 free slots is unrelated to the 2048 buffers we hand to the
pool, so `BM+0xdc[8:3]` is not a buffer count — more likely a queue-depth or
credit figure.

### Next

Find what sets `BM+0xdc` bits 28/30. The likely explanation is that **RX buffers
must be posted to a receive queue** separately from filling the general pool —
i.e. the bootloader arms the RX path in a way our init does not. That is the last
known difference between the two boots.


## Round 45: the vendor's free-list tables

Decoding `0x47f2f800` (the BM/pool init) revealed how the pool is really
populated — **not** by writing indices to `BM+0x10`, but by building
**free-list tables in DDR**:

```
r1 = 0x417ffffe; for (i = 0; i < 2048; i++) *(u16 *)(r1 += 2) = rev16(i);  -> 0x41800000
r1 = 0x41807ffe; for (i = 0; i <  512; i++) *(u16 *)(r1 += 2) = rev16(i);  -> 0x41808000
```

Big-endian u16 indices, and those two addresses are exactly the `TMC+0xe8` and
`TMC+0xec` pointers seen in the round-38 memory map — which finally explains
what those regions are.

Also recovered from the same function:

| register | value |
|---|---|
| `BM+0x00` | 0, then 1 to enable |
| `BM+0x04`, `BM+0x08` | `0x0104c040` |
| `BM+0x58` | 63 |
| `BM+0x5c` | 15 |
| `TMC+0xf4` / `TMC+0xf8` | `0x41000000` / `0x41400000` |
| `TMC+0xfc` | `0x08000800` |

### A misread worth recording

`str r4, [r3, #16]` in that function looks like `BM+0x10`, but `r3` at that point
holds the vendor's **RAM struct**, not the BM base. Writing `BM+0x10 = 0`
accordingly broke allocation outright (`tx_dropped` climbed, `tx_packets` stayed
0). Corrected.

### Result

All of the above is now implemented in `zx_eth_datapath_init()`. On a flash boot
TX works (`tx_packets=15, tx_dropped=0`) — but **RX is still dead**, and
`BM+0xdc` still reads `0x00000111` rather than the `0x50000111` seen after a
TFTP boot.

So building the free lists is necessary structure but not sufficient to arm RX.
The remaining difference is whatever sets `BM+0xdc` bits 28/30. Since the pool
tables, pool registers, ring bases, MAC control word and queue config now all
match a working boot, the next candidate is a *trigger* — an explicit "start
receive" write, or the RX queue needing buffers posted through a different
register than the one TX allocates from.


## Round 46: queue-table programming decoded (does not arm RX)

`0x47f2fb9c -> 0x47f2fa04` is a queue-table programming interface at
**`0x92344000`**:

```
wait for (base+0x18 & 1)
base+0x14 = index | (type << 22)     ; command, written FIRST
base+0x28 = cfg[3]                   ; then data words, descending
base+0x24 = cfg[2]
base+0x20 = cfg[1]
base+0x1c = cfg[0]
```

The vendor programs **400 entries of type 0** and **384 of type 2**, all with
`cfg = { 0x00800400, 0, 0, 0 }`. Implemented in `zx_eth_datapath_init()`.

Result: no change. On a flash boot TX still works (`tx_packets=16,
tx_dropped=0`), RX is still 0, and `BM+0xdc` still reads `0x00000111` versus
`0x50000111` after a TFTP boot.

Also checked and eliminated this round: `0x47f2f918` is merely `BM+0x00 = 1`
(already done), and `0x47f304b0` writes `0x923a0000 +0x10/+0x14 = 0`.

### Where this leaves RX-on-flash-boot

Everything the vendor's `eth_init` chain does is now reproduced: reset, global
init, NPP, BM registers and DDR free-list tables, pool/queue config, ring bases,
queue tables, MAC control word and per-port MAC registers. The register digest
matches a working TFTP boot in every field **except** `BM+0xdc` bits 28/30.

Since those bits do not respond to any configuration write found so far, the
likely explanation is that they are **status**, set as a side effect of the
receive path actually being armed by something still missing — plausibly the
part of U-Boot's flow that runs when it *uses* the interface (its `recv` loop
posting buffers), rather than in `eth_init`.

Next: trace what U-Boot does on its **first receive** (the `0x47f2feb4` path)
rather than in init - specifically any write that hands buffers to the RX queue
before polling, since that is the one code path exercised on a TFTP boot and
never on a flash boot.


## Round 47: MAC link programming implemented

Decoded the vendor's link-change path and implemented it properly.

`0x47f30578(port, speed, duplex)` programs `MAC+0x00`:

```
1000M : &= ~0x8000, |= 0x2000
else  : full -> |= 0xa000 ; half -> &= ~0x2000, |= 0x8000
        100M -> |= 0x4000 ; else &= ~0x4000
```

and `0x47f305c4(port)` then does `MAC+0x00 |= 3`.

`zx_eth_adjust_link()` previously only called `phy_print_status()` — it never
touched the MAC, so the MAC kept whatever mode the bootloader had left. That is
harmless after a TFTP boot (U-Boot had already programmed 1000M) but wrong in
general, and it is exactly the kind of thing that works on the bench and fails in
the field. It now applies the decoded formula on every link change.

Regression check — the TFTP path still works end to end:

```
4 packets transmitted, 4 packets received, 0% packet loss
```

(Latency is high, 146-586 ms, because RX is driven by a 1 ms poll timer with a
bounded ring scan rather than an interrupt. Functional, not yet fast.)

### Status of RX on a flash boot

Still unresolved. TX works (`tx_packets=16, tx_dropped=0`); RX stays 0 and
`BM+0xdc` still reads `0x00000111` instead of `0x50000111`.

Everything in the vendor's `eth_init` chain is now reproduced, including the
per-port link programming that was genuinely missing until this round. The
remaining difference is a single status field, and the only U-Boot code path not
yet mirrored is what runs while it actually *uses* the interface.


## Round 48: proving the init is incomplete — and a fast test loop

Until now "flash boot has no RX" could only be investigated by flashing and
rebooting (~5 min per attempt), and there was no way to tell whether our init was
*missing* something or *breaking* something.

A cleaner experiment settles it. On a **TFTP boot** the driver's init does not
normally run at all (the `MAC+0x00 & 0xffff0000` test sees the bootloader's
configuration), and Ethernet works with 0% packet loss. Forcing the init to run
anyway gives:

| configuration | result |
|---|---|
| bootloader init only (normal TFTP boot) | **0% packet loss** |
| + our init forced | 100% loss, `rx_packets=12` |
| + our init forced, reset skipped | 100% loss, `rx_packets=0` |

Two conclusions:

1. **Our `zx_eth_datapath_init()` is incomplete** — it disturbs a
   known-good datapath and cannot rebuild it. This is a stronger statement than
   "flash boot doesn't receive": the same defect is now reproducible on a TFTP
   boot, which is far quicker to iterate on than flashing.
2. **The reset is not the culprit.** Skipping it made RX strictly worse
   (12 -> 0 packets), so some other step in the sequence does the damage.

Remaining candidates to bisect, in rough order of invasiveness: the BM index fill
(2048 writes to `BM+0x10`, which may free buffers that are in use), the
784-entry queue-table programming, the DDR free-list tables, the ring-base
writes, and the pool/queue register block.

The driver is left with the init **conditional** again, and the working path
re-verified:

```
4 packets transmitted, 4 packets received, 0% packet loss
```


## Round 49: bisection — the reset is the destructive step

Using the round-48 loop (force our init on a working TFTP boot and see what
breaks), the init was bisected step by step:

| mask | ping |
|---|---|
| everything except BM index fill | 100% loss |
| **MAC registers only** | **0% loss** |
| MAC + reset + global + NPP + queue-cfg | 100% loss |
| MAC + reset + global | 100% loss |
| **MAC + global** (no reset) | **0% loss** |

So the destructive step is the **datapath reset** (`0x92000008`): writing it
tears down a working datapath that the remainder of our init cannot rebuild.

This **corrects round 48**, which concluded the reset was innocent. That test
skipped the reset but left every other step enabled, so it could not separate the
two effects; the clean bisection does.

`ZXI_MASK` in the driver now runs everything except the reset, and a bisection
mask is left in place so future steps can be isolated the same way.

### Flash boot still has no RX

With the reset removed, a flash boot still shows TX working
(`tx_packets=15, tx_dropped=0`) and RX at 0. So the reset was one real defect,
but not the reason RX never arms on a cold datapath.

What the bisection *does* establish is a clean split:

- Steps that are **safe** on a live datapath: MAC registers, global init.
- Steps that are **destructive**: the reset.
- Steps not yet individually cleared: NPP, queue-cfg, free lists, BM registers,
  BM fill, ring bases, queue tables — the "MAC + reset + global + NPP + queue-cfg"
  row was broken by the reset, so those four still need testing without it.

Next: with the reset gone, re-run the mask upward (MAC+global, then +NPP, then
+queue-cfg, ...) to find which remaining step is required for RX rather than
merely harmless.


## Round 50: the bootloader-init workaround does not exist

A tempting shortcut for the flash-boot RX problem was to have **U-Boot**
initialise Ethernet on every boot, since its `eth_init` demonstrably produces a
datapath where RX works. Confirmed that U-Boot's `ping` does run it:

```
=> ping 192.168.1.100
mac 0 phy status changed: 1000M full-duplex
-----smac_init
host 192.168.1.100 is alive
```

Two ways to hook that into every boot were tried, and **neither is executed** by
this board's autoboot flow:

| hook | result |
|---|---|
| `preboot="ping 192.168.1.100"` (saved) | never runs — no `smac_init` in the boot log |
| `bootcmd="ping 192.168.1.100"` (saved) | never runs — no `smac_init` in the boot log |

The ZTE `zteboot` autoboot path loads and starts the kernel through its own
logic, bypassing both variables. (`bootcmd` on this board only ever set
`bootargs`, which is itself a hint that it is not the boot trigger.)

So there is no bootloader-side workaround: the driver must arm the datapath
itself. The original `bootcmd` has been restored.

### Note for future work

Manually typing `ping` at the U-Boot prompt *does* arm the datapath, so the
existing bench workflow (TFTP boot, or any U-Boot network command before
booting) remains a valid way to get a fully working interface while the
driver-side initialisation is completed.


## Round 51: full-register diffing is not usable over the console

Attempted a wholesale comparison: dump every non-zero word of BM, TMC, TMQ, the
queue-programming block and MAC at `ndo_open()`, then diff a TFTP boot against a
flash boot on the host.

It does not work. The dump emits ~240 `pr_info` lines in a burst and console
rate-limiting silently drops them — the TFTP boot logged 243 lines while the
flash boot logged **none at all**. A naive read of that would have produced an
empty diff and the false conclusion "the register state is identical". The
instrumentation has been removed and the pitfall recorded.

### Confirmed side benefit of dropping the reset (round 49)

On a flash boot the ring-base register now reads correctly without any fallback:

```
zx279128-eth: rx ring=41a00000 tx ring=41c00000
zx279128-eth: ring_base=41a00000        (was 0x50009000 when we reset)
zx279128-eth eth0: port mode: MAC+0x00 00bb6002 -> 00bb6003
```

So removing the reset fixed the corrupted ring-base pointer as well — the
guard added in round 42 is now belt-and-braces rather than load-bearing.

### Current flash-boot state (verified)

```
root@OpenWrt:~# ip addr show br-lan
    inet 192.168.1.1/24 brd 192.168.1.255 scope global br-lan
eth0: tx_bytes=1510 tx_packets=11 tx_dropped=0   rx: 0
```

Link up at 1 Gbps, `eth0` bridged into `br-lan`, TX working, RX outstanding.

### If this is resumed

The productive next step is *not* more register archaeology. It is to make the
comparison reliable — e.g. dump into a kernel buffer and read it out through
`/sys` or `/proc` from userspace instead of the console, so a genuine full diff
between a bootloader-initialised and a driver-initialised datapath can be taken.
Everything else needed is already in place: a known-good reference boot, a
one-line reproduction (`BM+0xdc` reading `0x00000111` vs `0x50000111`), and a
bisection harness (`ZXI_MASK`).


## Round 52: reliable register diff via /proc

`/proc/zx_eth_regs` (seq_file) now dumps every non-zero word of BM, TMC, TMQ, the
queue-programming block and MAC. `cat` output goes through the tty rather than
`printk`, so it is not rate-limited — this is the reliable version of the round-51
attempt.

Captured on a **working TFTP boot** (ping 0% loss, 199 registers) and a **flash
boot** (172 registers), then diffed on the host. Selected differences:

**Present when working, absent on a flash boot**

```
MAC 004 00003ffe          <- never written by our init
MAC 008 80000001          <- never written by our init (bit31 looks like enable)
BM  0dc 50000111          <- the long-known symptom
BM  040/044/048/04c, 080..0d8   (pool state, many registers)
QP  01c ff803fff   QP 020 0100ff80   QP 024 00100200   QP 028 00000020
TMQ 03c 00400040   TMQ 048 00000009   TMQ 06c 07120712
TMC 100 00007711
```

**Different on a flash boot**

```
QP  01c 00800400   <- the value OUR queue-table init writes
TMC 100 00005500
TMQ 140/14c/150/158  (present only after our init)
```

Two immediately actionable findings:

1. `MAC+0x04` and `MAC+0x08` are never programmed by our init. Added
   (`0x00003ffe` / `0x80000001`) — verified flashed and booted, but **RX is still
   0**, so they are necessary-looking but not sufficient.
2. Our queue-table programming writes `{0x00800400, 0, 0, 0}`, while a working
   datapath ends up with `QP+0x1c = 0xff803fff`, `+0x20 = 0x0100ff80`,
   `+0x24 = 0x00100200`, `+0x28 = 0x00000020`. So the config struct taken from
   `0x47f2fb9c` is not the only one used — some other caller programs different
   entries with different values. That is the most concrete remaining lead.

### Method note

The earlier flash attempt in this round silently did nothing: the `tftp`/`nand`
commands were sent while the board was running **Linux**, not U-Boot, so they
went to the shell. Always power-cycle into U-Boot (catcher running) before
flashing, and check for `bytes written: OK`.


## Round 53: the missing type-4 queue, and the TMQ tables

Two concrete gaps were found by following the round-52 diff.

### 1. A third queue-programming call (type 4) — was missing

`0x47f2fb9c` makes **three** calls to the queue programmer, not two. The third
(`0x47f2fc00`) programs **index 0, type 4**:

```
cfg = { 0xff803fff, 0x0100ff80, 0x00100200, 0x00000020 }
```

which matches exactly what a working datapath shows at
`QP+0x1c/0x20/0x24/0x28`. Our init only programmed types 0 and 2. Added.

Effect: the **MAC block now matches the working boot register for register**
(`MAC 000/004/008/070/0b0/0b4/0d0/0d4/0dc/110/11c/120` all identical), which the
earlier round-52 additions alone did not achieve. RX still 0.

### 2. TMQ carries large tables we never write

The remaining diff is dominated by the TMQ block. A working datapath has ~80
registers set that ours does not, including a table of DDR pointers:

```
TMQ 240 41c03100   TMQ 244 41000010   TMQ 248 41c03110   TMQ 24c 41000010
TMQ 250 41023010   TMQ 254 41c030c0   ...   TMQ 2c4 41a03000   TMQ 2d0 41a02fb0
TMQ 284..2bc 000200xx      TMQ 300..33c small counts
TMQ 3d4/3d8/3dc 00010000 / 2100c400 / 0000018a
```

Those addresses (`0x41a02fb0`, `0x41c03100`, `0x41023010`) point inside the
datapath DDR window, i.e. this is per-queue descriptor/buffer bookkeeping.

**Replaying all 82 of those registers verbatim did not enable RX.** That is
informative: the tables are almost certainly *derived state* the hardware
maintains (pointers into rings it is actively managing), not pure configuration
that can be restored by writing values captured from another boot.

### Where this leaves it

`MAC`, `TMC`, `QP` now match a working datapath. What differs is BM pool
counters and the TMQ per-queue tables — both of which look like **runtime state
produced by the hardware once RX is genuinely armed**, rather than settings that
arm it. The next step should therefore target the *trigger* that makes the
hardware populate them, not the values themselves.


## Round 54: cleanup, and the RX ring handled properly

- Removed the 82 hard-coded TMQ register writes from round 53. They did not
  enable RX and hard-coding hardware-maintained state is the wrong shape of fix.
- The RX ring is now **fully cleared** in `ndo_open()`. Previously only the
  length halfword was cleared, because TX shared the ring and zeroing destroyed
  its control words; TX has had its own ring (`TMQ+0x60`) since round 38, so the
  RX ring can be given to the hardware clean.
- Regression checked: TFTP boot still `4 packets transmitted, 4 received,
  0% packet loss`.

Flash-boot RX remains unresolved.

## State of the Ethernet port

**Working and verified**

| capability | evidence |
|---|---|
| MDIO bus + 4 GE PHYs | PHY IDs `84b9:5031` at addresses 10-13 |
| Link management | 1 Gbps full duplex, MAC programmed on link change |
| Full datapath decode | BM, TM, queue programming, rings, descriptors, DDR map |
| TX | verified on the wire; correct lengths up to 1028-byte pings |
| RX | exact frame counts (30/30, 16/16, byte-perfect) |
| End-to-end | `ping` 0% packet loss over a TFTP boot |
| Flash boot | OpenWrt from NAND to shell, `eth0` in `br-lan`, link up, TX works |

**The one open defect**

RX does not arm when the driver initialises a cold datapath (flash boot). On a
bootloader-initialised datapath (TFTP boot) everything works.

Reduced to a single observable: `BM+0xdc` reads `0x50000111` when RX works and
`0x00000111` when it does not, and the TMQ per-queue tables stay empty.

Ruled out, each tested on hardware:

- missing init steps — the whole `eth_init` chain is reproduced; `MAC`, `TMC`
  and `QP` now match a working datapath register for register
- the datapath reset — proven destructive, removed
- bootloader-side workarounds — `preboot` and `bootcmd` are not executed by
  `zteboot`
- replaying the working TMQ tables verbatim
- pool filling via `BM+0x10`, via the DDR free-list tables, and both together

**Tooling left in place for whoever continues**

- `/proc/zx_eth_regs` — reliable full register dump (`cat`, not `printk`)
- `ZXI_MASK` — per-step bisection of the init sequence
- A known-good reference boot (TFTP) that can be diffed against any change


## Round 66: flash-boot RX localised — the MAC receives, the datapath does not

Two hypotheses were tested and eliminated first:

- **PP steering.** Round 28 measured `0x9238c000 +0x80/+0x88/+0xcc` as already
  set and concluded it was not the blocker — but that was on a *TFTP* boot,
  where the bootloader had programmed them. Applying them from the driver on a
  cold boot shows `+0xcc` is **already 1 even from cold**, and setting the others
  changes nothing. (Note `+0x80` *is* writable from cold, `0x3600 -> 0x301a`,
  whereas it ignores writes after a TFTP boot.)
- **PHY vendor registers.** U-Boot's per-port init (`0x47f305e4`) reads PHY reg
  30, writes 0 to it (page select), then reads reg 26 — that is **link-status
  polling, not configuration**, so phylib already covers it.

### The decisive measurement

`/proc/zx_eth_regs` was captured before and after injecting 40 frames into a
flash-booted board. Exactly two registers moved, both in the MAC:

```
MAC 0b0:  0        -> 0x00000020
MAC 0d0:  0x200    -> 0x0000020c
```

**Nothing in BM, TMC, TMQ or QP changed at all**, and `TMQ+0x11c` — the RX
counter U-Boot's own `recv` polls (`0x9235011c`, found by decoding
`0x47f2feb4`) — stayed at 0.

So on a flash boot the frames arrive, the PHY and MAC accept them and count
them, and then they are dropped at the **MAC-to-datapath handoff**: the buffer
manager and traffic manager never see them.

That is a much tighter statement than "RX does not work", and it rules out
everything downstream (ring layout, descriptor format, ownership bits, our poll
loop) — all of which are demonstrably correct, since the identical code receives
fine when the bootloader has initialised the datapath.

### Where to look next

The remaining difference between a working and non-working datapath is still
`BM+0xdc` (`0x50000111` vs `0x00000111`). Given this localisation, bits 28/30
most likely indicate that the buffer manager is ready to accept traffic from the
MACs. Filling the pool (`BM+0x10` writes) and building the DDR free lists do not
set them, so something else arms the BM input side — that is the thing to find.


## Round 67: the port attach mask (0x921d9000 + 0x68)

Decoding the tail of the vendor per-port init (`0x47f307dc..0x47f307e8`) shows a
read-modify-write that sets **the bit for this port** in `0x921d9000 + 0x68`,
immediately before enabling the MAC:

```asm
ldr  r3, [r7, #0x68]
tst  r9, r3
orr  r3, r3, r2, lsl r4     ; set bit <port>
str  r3, [r2, #0x68]        ; r2 = 0x921d9000
bl   0x47f305c4             ; then MAC+0x00 |= 3
```

This register had previously been written off in these notes as "link status,
reads 0 while link is up, probably unnecessary". That was wrong: it is a
**per-port attach mask**, and it reads **`0x00000000` on a cold boot** — i.e.
no port is attached to the datapath, which is precisely the failure localised in
round 66 (MAC counts frames, BM/TM never see them).

Setting it from `zx_eth_datapath_init()`:

```
zx-eth: port attach +68 00000000 -> 0000000f
```

### Result: real change, still not RX

With the mask set, the datapath now *reacts* to incoming traffic — `TMC+0x100`
changes when frames arrive, where previously **only MAC counters moved and
nothing in BM/TMC/TMQ responded at all**. But `rx_packets` is still 0 and ping
still fails.

So the attach mask is necessary (it was genuinely missing) but not sufficient.
The frames now get one step further into the datapath and are still not being
buffered into the ring.

The change is kept: it is demonstrably part of the vendor sequence and it
measurably moves the datapath state.


## Round 68: the working datapath runs two BM queues, ours runs one

### Correction: the DDR free lists alone are enough

Round 43 added an explicit fill (writing every buffer index to `BM+0x10`) because
that was what made TX allocate, and round 45 kept it alongside the vendor's DDR
free-list tables "until the interaction is understood". Removing it now: **TX
still works** (`tx_packets=13, tx_dropped=0`). So the tables are sufficient and
the extra fill was redundant. Removed.

### The remaining BM difference is structural, not cosmetic

Comparing every BM register on a cold flash boot against a working TFTP boot,
the **static configuration matches exactly** (`000, 004, 008, 028, 02c, 030,
034, 058, 05c, 0cc, 0d0`). What differs is a clear pattern:

| offset | cold | working |
|---|---|---|
| 040 | `0004004f` | `00630014` |
| **044** | *(zero)* | `00500001` |
| 048 | `07400000` | `00000050` |
| **04c** | *(zero)* | `00000050` |
| 080 | `00000740` | `000007b0` |
| **084** | *(zero)* | `000001b0` |
| 088 | `000000b5` | `0000004f` |
| **08c** | *(zero)* | `0000004f` |
| 090 | `0000000f` | `00000e14` |
| **094** | *(zero)* | `00000001` |
| 0b0 | `00000001` | `00000702` |
| **0b4** | *(zero)* | `00000001` |
| 0dc | `00000111` | `50000111` |

The working registers come in **pairs** — `040/044`, `048/04c`, `080/084`,
`088/08c`, `090/094`, `0b0/0b4` — and on a cold boot only the *first* of each
pair is ever non-zero.

That reads as **two buffer-manager queues in service on a working datapath and
only one on ours**. Given round 66 showed frames stop at the MAC-to-datapath
handoff and round 67 got them as far as `TMC`, the missing second queue is very
likely the receive queue.

### Next

Find what brings up the second BM queue. The queue-programming block at
`0x92344000` (types 0, 2 and 4, round 53) is the obvious place to look for a
per-queue enable that we are only applying to queue 0.


### Round 69: BM+0x00 is not a per-queue enable

Tested the natural reading of round 68's pairing: that `BM+0x00` is a per-queue
enable bitmask and we only ever set queue 0. Writing `3`:

```
BM+0x00 reads back 00000001      <- bit 1 is not writable
040=00050050  044=(zero)   048=07400000  04c=(zero)
080=00000740  084=(zero)   088=000000b5  08c=(zero)
090=00000010  094=(zero)   0b0=00000001  0b4=(zero)
```

So `BM+0x00` is a single global enable, the second queue did not appear, and RX
is unchanged. Reverted.

What still holds from round 68: a working datapath has the second register of
each pair populated and ours never does, and the vendor does program **two**
per-queue configs (`BM+0x04`, `BM+0x08`) and build **two** free-list tables
(2048 + 512 entries) — both of which we already replicate. So the second queue
is created by something else entirely, not by a bit in `BM+0x00`.

### Running list of what has been eliminated for flash-boot RX

| candidate | verdict |
|---|---|
| missing init steps (`eth_init` chain) | all reproduced; `MAC`/`TMC`/`QP` match a working datapath |
| datapath reset | proven destructive, removed |
| ring bases, descriptor layout, ownership bit | correct — identical code receives fine after a bootloader init |
| pool filling (`BM+0x10`, DDR tables, both) | tables alone are sufficient; extra fill removed |
| PP steering (`0x9238c000`) | `+0xcc` already 1 even from cold |
| PHY vendor regs 26/30 | link-status polling, not configuration |
| port attach mask (`0x921d9000+0x68`) | **was genuinely missing**; now set; advanced frames to `TMC` |
| `BM+0x00` as per-queue enable | bit 1 not writable |


## Round 70: vendor init ordering breaks TX — and a round-68 correction

### The BM+0x10 fill IS required (round 68 was wrong)

Round 68 reported that the DDR free-list tables alone were sufficient and the
explicit `BM+0x10` fill was redundant. **That was wrong.** The edit which
"removed" the fill matched a stale copy of the text, so the `ZXI_BMFILL` loop
was still running and TX kept working — the measurement supported a change that
had not actually been made.

Removing it for real:

```
BM+0x10 reads 0   (instead of 0x7ff)
eth0: tx_packets=0  tx_dropped=10
```

So the pool is **not** populated by the DDR tables alone; the explicit fill is
required. Restored, and TX verified back at `tx_packets=13, tx_dropped=0`.

Lesson: after any edit that is supposed to remove behaviour, confirm the
behaviour actually changed — not just that the build succeeded.

### Vendor init ordering does not transplant

The vendor sequence (`0x47f2f800` then `0x47f2f918`) is:

1. disable BM, write per-queue config
2. build the DDR free-list tables
3. point TMC at pool/tables/rings
4. enable BM last

That exact order was implemented and **breaks buffer allocation on this
driver** — every transmit dropped. The order that works here is the reverse:
TMC pointers first, then tables, then BM config and enable. The source now
carries a warning not to "fix" this to match the vendor without re-testing TX.

Flash-boot state is back to: link up, TX working, RX still 0.


## Round 70b: the packet processor is dead on a cold boot

Two external research passes (web) produced the breakthrough direction. Key
inputs:

- The stock device tree names blocks this driver had never touched:
  `npp@0x921c0000`, **`idm@0x921c8000`**, **`sw@0x92300000`** (Ethernet switch),
  `tm@0x92340000`, `pp@0x92380000`.
  **Correction:** round 32 probed `0x92300000` as "MAC port 4", found it
  all-zero, and concluded there was no separate CPU port. That address is not a
  MAC port at all — it is the **switch** block.
- For BM/TM datapaths generally (Marvell mvneta_bm / mvpp2, NXP DPAA), the
  standard causes of "MAC counts frames but the buffer manager never sees them"
  are: pool never seeded, port->pool binding missing, port->queue binding
  missing, per-RXQ enable bit clear, or **the classifier having no default flow**.
  Marvell's `mvpp2_prs_def_flow()` and DPAA's `dflt_fqid` are the analogues.

### Measurement

Dumping the previously-unexamined blocks and diffing a working TFTP boot against
a cold flash boot:

```
present when WORKING, absent when COLD:
  PP 000 00000001        <- packet processor enable
  PP 09c 00002200   PP 0a0 00000033   PP 0a4 003b2200   PP 0a8 00100000
  PP 0ac 00003322   PP 0b0 006d064f   PP 0b4 00220022   PP 0b8 00330033
  PP 0c0..0e4  (flow/port map block)
  PP 104 000242f0   PP 10c 00000411   PP 110 22008e3f   PP 118 f000107c
  SW 114 00020000
```

So on a cold boot the **entire packet processor is unconfigured**, including its
enable bit — precisely the "classifier has no route, frame dies after the MAC"
failure mode.

### But the PP cannot be written yet

Writing the enable bit does nothing:

```
zx-eth: PP enable +00 00000000 -> 00000000
```

The register does not accept the write, so the PP block is **not clocked or not
out of reset** on a cold boot. That is the next thing to fix: find the clock
gate / reset for `pp@0x92380000` (and probably `npp@0x921c0000`,
`idm@0x921c8000`, `sw@0x92300000` too) and release it before programming.

This is the first mechanism that explains *all* the evidence: MAC counts frames,
nothing downstream reacts, and every attempt to program downstream blocks from
cold has silently done nothing.


## Round 71: reset is safe from cold; clock gating is NOT the difference

### Correcting round 49

Round 49 bisected the datapath reset (`0x92000008`) as "destructive" and removed
it. That bisection forced our init to run on a **TFTP boot** — i.e. on a
datapath the bootloader had already brought up and was actively using. Resetting
a live datapath is obviously harmful and says nothing about the cold case, which
is the only case where this init actually runs.

Re-enabled for cold boots and verified: TX is unaffected
(`tx_packets=18, tx_dropped=0`). `ZXI_MASK` is back to `0x3ff` (all steps).

### But the reset does not release the packet processor

```
zx-eth: port attach +68 00000000 -> 0000000f     (takes)
zx-eth: PP enable   +00 00000000 -> 00000000     (does not take)
```

### And the clock/reset manager is identical in both states

The stock DTS has `topcrm@94000000` (`zte,ZX279127-topcrm`, syscon) and the
`pp`/`npp`/`tm` nodes carry **no `clocks` property**, so their gating must live
there. Dumping all of `0x94000000` on a working TFTP boot and a cold flash boot:

```
cold = 19 non-zero registers, working = 19, differences: NONE
```

So the packet processor is **not** held in reset or clock-gated by topcrm — the
clock-gating hypothesis from the research checklist is eliminated. `PP+0x00`
refuses writes from cold for some other reason (a lock, a required sequence, or
a dependency on another block being brought up first).

Also noted from the stock DTS: `idm@921c8000` is `status = "disabled"`, so the
IDM block is not used by the vendor firmware and can be ignored.


## Round 72: the datapath island is write-blocked from cold

### Writability probe

Writing known-good values (captured from a working boot, not blind patterns) to
the PP and switch blocks on a cold boot:

```
PP  +00  00000000 -> 00000000     write ignored
PP  +9c  00000000 -> 00000000     write ignored
PP  +104 000002f0 -> 000002f0     write ignored - but READS non-zero
SW  +114 00000000 -> 00000000     write ignored
```

So the blocks are **powered and readable with sensible content** — `PP+0x104`
holds `0x2f0` cold versus `0x242f0` working — but the entire region **rejects
writes**. This is not a missing enable bit inside the PP; the register interface
itself is not accepting writes.

Note this also means our `0x923a0000 + 0xe0 = 17` init write has been silently
doing nothing: `0x923a0000` lies inside the PP node's range
(`pp@92380000`, size `0x40000`).

### A real bug found and fixed: the reset delays were 1000x too short

The vendor reset is:

```asm
r3 = [0x92000008] ; r0 = r3 & ~mask ; [0x92000008] = r0
mov r0, #10 ; bl 0x47f25380      <- 0x47f25380 loops udelay(1000) => mdelay
[0x92000008] = 0xffffffff
```

`0x47f25380` is **mdelay**, so the vendor waits **10 ms**; our code used
`udelay(10)`. The global init's delay was likewise `mdelay(20)` against our
`udelay(20)`. Both corrected — this is a genuine defect regardless of its effect
here.

(The caller passes `mvn r0, #0`, i.e. mask = all bits, so clearing every bit was
correct.)

Result: the corrected delays did **not** unlock the region. TX remains fine
(`tx_packets=15`).

### What this means

Every attempt from round 66 onward to program PP/SW state from cold has been
writing into a region that silently discards writes. The question is no longer
"which PP register arms RX" but **"what makes this register region writable at
all"** — a bus/firewall/permission gate, or a handshake the vendor performs
before touching the block.


## Round 73: CORRECTION — the PP registers are state, not configuration

Round 70b concluded that "the entire packet processor is unconfigured on a cold
boot" because a block of PP registers is present on a working TFTP boot and
absent on a cold flash boot. **That was mistaking effect for cause.**

Two measurements refute it:

1. **The PP region ignores CPU writes even when RX is working.** Probing on a
   normal, fully-functional TFTP boot:

   ```
   PPWRITE probe: +9c 00001a00, wrote 00001a01, reads 00001a00
   ```

   The register is not writable from the CPU in *either* state, so "we failed to
   program it from cold" was never the difference — nobody can program it from
   the CPU.

2. **The values are not stable.** `PP+0x9c` read `0x2200` on one working boot and
   `0x1a00` on another. Configuration does not drift between boots; counters and
   pipeline state do.

So the PP block is populated **because traffic is flowing**, not in order to make
it flow — the same trap as the round-53 TMQ tables, which were also replayed
verbatim to no effect.

All PP/SW write attempts have been removed from the driver, with a comment
recording why they cannot work. Connectivity re-verified on the working path
after the probe: `3 packets transmitted, 3 received, 0% packet loss`.

### Consequence for the search

Rounds 66-72 were built on the premise that some register in the
MAC->datapath path was missing a value we could write. That premise is now
disproved for the PP and switch blocks. What remains writable and therefore
still candidate territory: BM (`0x92348000`), TM (`0x92340000`/`0x92350000`), the
port attach mask (`0x921d9000`), the MAC blocks, and the queue-programming
window (`0x92344000`) — all of which we already program.

The kept results from those rounds are the genuine ones: the **port attach mask**
(really was missing, really does change datapath behaviour) and the **mdelay
fix** (reset delays were 1000x too short).


## Round 74: PROOF that the driver is correct and the gap is purely our init

The single most useful experiment of this investigation. Boot the **flashed**
kernel out of NAND, but let U-Boot run `eth_init` first:

```
=> ping 192.168.1.100          # runs eth_init: prints -----smac_init
=> nand read 0x42000000 0x700000 0x300000
=> bootm 0x42000020            # +0x20 skips the 32-byte ZTE image header
...
root@OpenWrt:~# ping -c 4 192.168.1.100
4 packets transmitted, 4 packets received, 0% packet loss
eth0: rx_packets=5  tx_packets=25
```

Identical kernel image, identical rootfs, identical driver — the only difference
from a failing flash boot is that the bootloader touched the network first.

This establishes three things cleanly:

1. **The Ethernet driver is correct.** TX, RX, NAPI, descriptor handling, ring
   management and the MAC/PHY layer all work against a properly initialised
   datapath, booting from flash, with no TFTP involved.
2. **The gap is entirely `zx_eth_datapath_init()`.** Whatever U-Boot's
   `eth_init` does, our reproduction of it is still incomplete — despite
   matching every register write we have been able to find.
3. **It is not about traffic.** A single `ping` is enough; no bulk transfer or
   sustained RX is required. So the missing piece is part of the *init
   sequence*, not something that only happens while data flows.

### Practical consequence

The device is fully usable today, from flash, if the bootloader initialises
Ethernet first. That makes this a working bring-up rather than a blocked one:

```
=> ping <any address>
=> nand read 0x42000000 0x700000 0x300000
=> bootm 0x42000020
```

### Also tested this round

Re-applying the port attach mask on the link-up transition (in case the vendor's
link-conditional ordering mattered) is a no-op — the mask already reads `0xf`
from probe time:

```
link-up attach +68 0000000f -> 0000000f
```


## Round 75: dumping eth_init from U-Boot itself

The right way to find what `eth_init` does was not to keep reading disassembly —
it was to dump the registers **from the U-Boot prompt**, before and after a bare
`ping`, with Linux out of the picture entirely:

```
=> md 0x92348000 40      (before)
=> ping 192.168.1.100    (runs eth_init, nothing else)
=> md 0x92348000 40      (after)
```

### What eth_init actually changes

**BM (27 registers).** Ones we already wrote: `+0x00` (0->1), `+0x04`/`+0x08`
(`0005c040` -> `0104c040`). Ones we were **missing entirely**:

```
+0x40 0 -> 00540005    +0x44 0 -> 00500001    +0x48 0 -> 00000050
+0x4c 0 -> 00000050    +0x50 0a -> 0          +0x54 0a -> 0
+0xc8 0 -> 00000200    +0xcc 02022000 -> 04022000
+0xd0 0 -> 07f00000    +0xd8 0 -> 00004000
```

**TMC (6 registers)** — all ones we already write, and note the cold values are
garbage (`+0xf0` reads `50009000` before init), confirming the round-42 fallback
was justified.

**`0x921d9000` (port attach): 0 registers changed.** So `eth_init` does not
touch it — our setting it is an extra, not part of this sequence.

Also learned: `BM+0x58`/`+0x5c` are count-minus-one registers — writing 63 and 15
reads back `0x40` and `0x10`, which matches the vendor. Our values were right.

### Result

The missing BM configuration is now written, and the block matches the working
state almost exactly:

```
off   cold       u-boot     match
000   00000001   00000001   OK       044   00500001   00500001   OK
004   0104c040   0104c040   OK       058   00000040   00000040   OK
008   0104c040   0104c040   OK       05c   00000010   00000010   OK
0c8   00000200   00000200   OK       0cc   04022000   04022000   OK
0d0   07f00000   07f00000   OK       0d8   00004000   00004000   OK
040   00360081   00540005   DIFF (drifts - counter)
048   07700080   00000050   DIFF (drifts - counter)
04c   000000a0   00000050   DIFF (drifts - counter)
0dc   00000111   50000111   DIFF (status bits 28/30 still absent)
```

RX still does not work, but the configuration gap is now closed to three
drifting counters and the `BM+0xdc` status bits — the same two bits that have
marked the difference since round 44.


## Round 76: three real bugs found by diffing the rest of eth_init

Extending the U-Boot before/after dump to the remaining blocks found three
genuine defects in our init.

### 1. MAC register offsets were wrong

`eth_init` writes `MAC+0xb0` and `MAC+0xd0`. This driver wrote `+0xb00`,
`+0xd00` and `+0xd30` — an extra zero in each offset, so three writes had been
landing in unrelated registers since round 42. Corrected.

### 2. TMQ configuration was missing

`eth_init` writes `TMQ+0x3c = 0x00400040` and `TMQ+0x48 = 0x00000008`; we wrote
neither. Added.

### 3. Type-4 queue programming is 384 entries, not one

After `eth_init`, `QP+0x14` reads **`0x0100017f`** — type 4 (`4 << 22`) with
index `0x17f` = 383, i.e. the last of a **384-entry loop**. Round 53 read the
disassembly as a single index-0 write and programmed exactly one entry. Fixed to
loop 0..383, and it now reproduces the vendor value exactly.

### Blocks eth_init does NOT touch

`NPP` (`0x921c0000`) and `PON` (`0x92000000`): **zero registers changed**. Our
init writes NPP registers; those writes are harmless but pointless.

### Result

Configuration now matches a bootloader-initialised datapath on 13 of 16 checked
registers:

```
MAC 000/004/008/070/0b4  OK      QP 014/01c/020/024/028  OK
TMQ 03c/050/060          OK
MAC 0b0  cold=00000000 uboot=00000020   DIFF - reads back as a counter
MAC 0d0  cold=00000200 uboot=0000000c   DIFF - reads back as a counter
TMQ 048  cold=00000000 uboot=00000008   DIFF - write does not stick
```

The three remaining differences all behave as hardware-maintained values rather
than settings.

RX still does not work on a cold boot. But the init is now demonstrably much
closer to the vendor's, and two of the three fixes (wrong MAC offsets, the
384-entry type-4 loop) were real bugs that would have mattered regardless.


## Round 77: free lists are fine; and the real asymmetry with U-Boot

### The DDR free-list tables are correct

Added a barrier and read-back after building them (they live in a
write-combining mapping, so stale memory was a plausible cause):

```
freelist1 readback [0]=0000 [1]=0100 [2047]=ff07
freelist2 readback [0]=0000 [511]=ff01
```

Those are exactly the expected big-endian indices (`0`, `1`, `0x7ff`, `0x1ff`),
so the tables really are in DDR before the BM is enabled. Not the bug. The
barrier is kept — writing a hardware-consumed table through a WC mapping without
one was a latent defect regardless.

### The asymmetry that matters

`eth_init`'s register diff does **not** include `BM+0x10`. U-Boot never pushes
buffer indices into the pool by hand — its pool is fed entirely by the DDR
free-list tables. Our driver, by contrast, *requires* the explicit `BM+0x10`
fill or every transmit is dropped.

That is the sharpest statement of the remaining gap: **the hardware is not
consuming our free-list tables.** It also fits `BM+0xdc` never gaining bits
28/30 on a cold boot, if those indicate "pool loaded from the free list".

### Correction to round 70

Round 70 concluded that the vendor's init ordering "breaks buffer allocation".
It does not — that test simultaneously lost the `BM+0x10` fill (the stale-text
edit described in the same round), and the fill was the actual cause. Retested
properly with vendor ordering **and** the fill retained: TX works normally
(`tx_packets=15, tx_dropped=0`). The ordering is now the vendor's.

RX on a cold boot remains unfixed.


## Round 78: CORRECTION — BM+0xdc was never the marker

U-Boot's prompt gives an interactive register environment on a **cold** datapath.
Replaying our exact init there:

```
PRE   (cold)                       923480dc: 00000110
MID   (all our BM config writes)   923480dc: 00000110    <- config changes nothing
POST  (BM+0x00 = 1)                923480dc: 00000111    <- same value Linux reaches
+ TMC pointers, re-enable          923480dc: 00000111
```

Then the control — a real `ping`, i.e. the genuine `eth_init`, in the same
session:

```
host 192.168.1.100 is alive
AFTERPING                          923480dc: 00000111    <- NOT 0x50000111
md 0x41800000                      01000000 03000200 05000400 07000600
```

Two conclusions:

1. **`eth_init` leaves `BM+0xdc` at `0x111`, exactly what our cold init
   produces.** The `0x50000111` seen in round 44 and after was captured from a
   *running Linux system with RX active*. Those bits are set while the receive
   path is working — they are an **effect of RX, not a precondition for it**.
   The search that rounds 44-77 organised around "what sets BM+0xdc bits 28/30"
   was chasing a symptom.
2. The free-list table content after `eth_init` (`01000000 03000200 ...`) is
   byte-for-byte what our driver writes, confirming round 77's read-back.

So the BM register state after our init genuinely matches the bootloader's. The
cold-boot RX difference is **not** in the BM or TMC register state at all, which
retires the whole line of investigation from round 44 onward.

### Where that leaves it

Known good: our BM/TMC/QP/MAC configuration now matches `eth_init` register for
register (round 76), the free lists are correct in DDR (round 77), and the
driver is proven correct against a bootloader-initialised datapath (round 74).
Whatever `eth_init` does that we do not, it does not show up in any register we
have dumped — which points at the PHY/SerDes bring-up path or an ordering
relationship with link establishment, not at datapath configuration.


## Round 79: eth_init's full footprint, and a latent duplicate-code bug

### eth_init touches nothing else

Diffed the last unexamined blocks across `eth_init`:

```
GEPHY0 (0x9b000000): 0 registers changed
GEPHY1 (0x9b100000): 0 registers changed
SW     (0x92300000): 0 registers changed
```

Combined with round 76 (NPP and PON also unchanged), `eth_init`'s **entire**
register footprint is now known: **BM (27) + TMC (6) + MAC (7) + TMQ (7) +
QP (5)** — every one of which this driver now reproduces.

### Tested and negative: ordering relative to link-up

U-Boot runs `eth_init` only once the PHY link is established, while we ran it at
probe (~8 s) mid-autonegotiation. The whole datapath init is now deferred to the
first link-up:

```
[   7.889] datapath cold - deferring init to first link-up
[  49.007] link up - running deferred datapath init
```

It works exactly as intended and **does not fix RX**. So link ordering is not
the difference. The deferred structure is kept — it matches the vendor's
ordering and is more correct regardless.

### Real bug fixed: duplicated probe block

Repeated structural edits to this file had left **two copies** of a ~40-line
probe region (ring mapping, cold-datapath detection, info prints). The cold
detection was running twice, visible as a doubled log line. Removed, along with
an orphaned PP writability probe left over from round 73. The file now has a
single copy of each and the working path is re-verified:

```
3 packets transmitted, 3 received, 0% packet loss   (TFTP boot)
"datapath cold" not printed   - correctly skipped when the bootloader inited
```

### Status of the cold-boot RX search

Everything `eth_init` writes is reproduced; the free lists are correct in DDR;
BM/TMC/QP/MAC state matches; PP/SW/GEPHY/NPP/PON are untouched by `eth_init`;
`BM+0xdc` was a red herring; link ordering is not it. The difference is not in
any register that has been dumped, on either side of the boundary.


## Round 80: diffing DDR, not registers

Every previous diff looked at registers. `eth_init` also writes **memory**, and
that had never been compared. Dumping the DDR regions from U-Boot before and
after a `ping`:

### What eth_init/traffic puts in DDR (working reference)

```
RX ring 0x41a00000:  00000191 00090000 20007800 000000f0
                     0000019e 00090000 20007800 000400f0
TX ring 0x41c00000:  00000080 00010000 21005400 000000aa
pool    0x41000000:  +0x10 onwards = the Ethernet frame itself
region  0x41400000:  0 changed
```

This independently confirms three formats the driver derived the hard way:

- RX descriptors carry **`0x20` in w2 byte 3** — the ownership marker we scan for.
- TX descriptors carry **`0x21` in w2 byte 3** — exactly the round-40 fix.
- `w3 >> 2` is the length (`0xaa >> 2` = 42, an ARP), and the buffer payload
  starts at **+0x10**, confirming `BUF_HDR = 16`.

### What our cold boot produces

```
RXRING 0..3   all zeros                            <- nothing, even after traffic
TXRING 0      00000080 82010000 2100ac0e 0000015a
TXRING 1      00000080 84010000 2100b40e 0000016a
```

**The RX ring is completely untouched.** The hardware writes no receive
descriptors at all, which matches round 66 (frames counted by the MAC, nothing
downstream) and rules out any possibility that RX descriptors are being produced
somewhere our driver fails to look.

### A discrepancy worth chasing

Our TX descriptors do not encode the buffer index the way U-Boot's do:

```
        w1         w2
U-Boot  00010000   21005400     byte7=0x00, w2 byte0=0x00   (buffer 0)
ours    82010000   2100ac0e     byte7=0x82, w2 byte0=0x0e
```

`w1` byte 7 should be `idx << 1` and `w2` byte 0 should be `idx >> 7`. For our
allocated index those two disagree with each other (`0x82 >> 1` = 65, but
`0x0e` implies a much larger index), so the packing of the index across the two
fields is suspect. TX works regardless — the length and buffer contents are
right — but this is the first concrete inconsistency found in our descriptor
construction and is worth resolving.


## Round 81: correcting round 80, and trimming our init to eth_init's footprint

### Correction: the TX index encoding was fine

Round 80 flagged our TX descriptor index packing as inconsistent
(`w1` byte7 = `0x82` vs `w2` byte0 = `0x0e`). That was an arithmetic error on my
part. The encoding is `idx & 0x7f` in byte7 (shifted left 1) and `idx >> 7` in
byte8:

```
byte7 = 0x82 -> (0x82 >> 1) = 65     byte8 = 0x0e -> 14
idx = 14 * 128 + 65 = 1857           valid buffer index
```

Both fields agree; there is no bug. U-Boot simply happened to be using buffer 0.

### Writes we make that eth_init does not

Checking our init against the now fully-characterised `eth_init` footprint
(BM/TMC/MAC/TMQ/QP only) turned up several writes we invented:

| our write | evidence |
|---|---|
| `TMC+0x04 = 16` | not in the TMC diff — eth_init changes only `+0xe8..+0xfc` |
| port attach `0x921d9000+0x68` | eth_init changes **0** registers there |
| PP steering `0x9238c000` | eth_init changes 0 registers in the PP block |
| NPP `0x921c0000` | eth_init changes 0 registers there |
| `0x923a0000+0xe0` | inside the PP range, which ignores writes entirely |

All of these are now disabled — each backed by a measured diff.

### And one I disabled without evidence

I also disabled the queue/pool config at `0x921d4000`, and that was **not**
justified: round 76 diffed `0x92344000`, a *different* block, and `0x921d4000`
has never been dumped across `eth_init` at all. That build panicked in userspace
(`Attempted to kill init`, `Comm: procd`). Restored, with a note in the source
that there is no evidence for removing it.

Working path re-verified after the change: `3 packets transmitted, 3 received,
0% packet loss`, 9 MTD partitions.


## Round 82: our init now provably matches eth_init — and RX still fails

Diffed the last unmeasured block, `0x921d4000`:

```
+0x000  ffffffff -> 30000000      +0x004  ffffffff -> 00008800
+0x040  ffffffff -> 30000000      +0x044  ffffffff -> 00008800
+0x28c..+0x2a4   0 -> 1   (exactly 7 registers)
0x921d9000       0 changed   (sample 04444444)
```

Our driver writes precisely those values, including exactly those seven queue
enables — so the round-81 removal really was unjustified, and `0x921d9000`
really is an invention of ours.

### Complete accounting

| block | eth_init writes | we match |
|---|---|---|
| BM `0x92348000` | 27 registers | yes (rounds 75-76) |
| TMC `0x92340000` | 6 registers | yes |
| MAC `0x92200000` | 7 registers | yes (offsets fixed round 76) |
| TMQ `0x92350000` | 7 registers | yes (round 76) |
| QP `0x92344000` | 5 registers, 384-entry type-4 loop | yes (round 76) |
| `0x921d4000` | 4 + 7 registers | yes (this round) |
| NPP, PON, PP, SW, GEPHY, `0x921d9000` | **0 registers** | we no longer touch them |

Cold boot with this exact-footprint init: **RX still 0**, TX fine
(`tx_packets=16`).

### What that means

The cold-boot RX failure is **not** explained by any register write in
`eth_init`. Every value, every block, and now every non-write has been matched
against the bootloader. The remaining candidates are ordering/timing within the
sequence, or something U-Boot's network stack does outside `eth_init` proper —
for example programming the station MAC address (there is a
`0x47f3031c` "MAC addr" routine in the vendor code that this driver has never
called; our driver uses `eth_hw_addr_random()`).

That last one is concrete and untested, and is the obvious next step.


## Round 82b: the station MAC — and a likely root cause

The vendor programs the station MAC address from `0x47f3031c` -> `0x47f2f6c8`:

```
0x923a0078 + port*8 = mac[2]<<24 | mac[3]<<16 | mac[4]<<8 | mac[5]
0x923a007c + port*8 = mac[0]<<8  | mac[1]
```

(stock MAC in the bootloader image: `00:d0:d0:01:02:03`)

This driver has **never** written those registers. That fits the symptom
perfectly — transmit does not need a station address, receive filtering does.

### But Linux cannot write them

```
zx279128-eth eth0: hw mac port0: +78=00000000 +7c=00000000
```

The writes are discarded. `0x923a0078` lies inside the `pp@92380000` range
(size `0x40000`), and round 72 established that this whole region ignores CPU
writes, with round 73 showing it is unwritable **even on a boot where RX is
working**.

### The pattern across all of it

| actor | can write PP region (incl. station MAC) |
|---|---|
| U-Boot | **yes** — it programs the MAC and the PP block during `eth_init` |
| Linux | **no** — every write discarded, in both cold and working boots |

A privilege boundary is the natural explanation: this is a Cortex-A9 with
TrustZone, U-Boot runs in the **secure** world, and the packet processor and
station-MAC registers appear to be secure-only. Linux boots non-secure and
simply cannot reach them.

If that is right it explains the entire investigation: our datapath init can
match `eth_init` register-for-register on every block Linux *can* write (rounds
75-82) and still never receive, because the piece that actually arms reception
lives behind a barrier Linux cannot cross. It also explains why the documented
workaround works - letting U-Boot run `eth_init` performs those writes from the
secure world before Linux starts.

**Next step to confirm:** check the CPU mode Linux is running in (SCR.NS), and
whether U-Boot switches to non-secure before `bootm`. If confirmed, the fix is
either to have U-Boot perform the datapath init (the current workaround, made
automatic), or to add a secure-monitor call, not to keep hunting registers.


## Round 83: RETRACTION — both round-82 hypotheses are wrong

Round 82 proposed (a) that the station MAC at `0x923a0078` was the missing write
and (b) that a TrustZone boundary let U-Boot write it while Linux could not.
Tested from the U-Boot prompt; **both are false**.

```
cold, before eth_init:
  md 0x923a0078      -> 00000000 00000000
  mw 0x923a0078 0xdeadbeef
  md 0x923a0078      -> 00000000 00000000     <- U-Boot's write ignored too
  md 0x9238009c      -> 00000000
  mw 0x9238009c 0x12345678
  md 0x9238009c      -> 00000000              <- ignored

after `ping` (eth_init runs, RX demonstrably works):
  md 0x923a0078      -> 00000000 00000000     <- station MAC NEVER programmed
  md 0x9238009c      -> 00000200              <- changed by hardware, not by us
  mw 0x9238009c 0x12345678
  md 0x9238009c      -> 00000200              <- still ignored
```

1. **Not TrustZone.** U-Boot cannot write these registers either, in any state.
   The asymmetry I inferred between U-Boot and Linux does not exist — I had only
   ever tested writes from Linux.
2. **Not the station MAC.** `0x923a0078` reads zero on a boot where receive
   works perfectly, so the vendor's MAC routine either is not called by `ping`
   or targets something else. Either way it is not what arms RX.
3. **Confirmed for good:** the whole PP region is read-only to the CPU from both
   U-Boot and Linux, and its values change on their own. Round 73's reading was
   right — these are hardware-maintained status registers, and no amount of
   writing them will do anything.

The `zx_eth_set_hw_mac()` call added in round 82 is therefore useless; it is
kept only as a documented negative (it logs `+78=00000000` and changes nothing).

### Standing summary of the cold-boot RX problem

- The driver is correct (round 74: flash boot + U-Boot `eth_init` = 0% loss).
- Our init matches `eth_init` on every block that is writable at all
  (rounds 75-82).
- The blocks `eth_init` does not touch, we no longer touch (round 81).
- The free lists are byte-correct in DDR (round 77).
- The hardware writes zero RX descriptors on a cold boot (round 80).
- `BM+0xdc`, the PP block, the station MAC, clock gating, link ordering and
  TrustZone are all eliminated.

What `eth_init` does that we cannot reproduce is still unidentified, and it is
not any register write that a CPU can perform.


## Round 84: an entire branch of eth_init we never decoded

### Methodological correction

Round 83 concluded the cause "is not any register write a CPU can perform".
That was wrong, and wrong in an important way: `eth_init` *is* nothing but CPU
register writes. The real problem is that a **readback diff cannot see
write-only or self-clearing registers** — which is exactly what was being
missed.

### The missing branch

`0x47f2f748` (global init) calls three functions. Two were known
(`0x47f2fd28`, `0x47f308c4`); **`0x47f304b0` had never been decoded**. It does:

```
0x47f304d8:   [0x92380000 + 0x00] = 2      <- PP command register
              udelay(1000)
0x47f30440:   configure 0x92388000  (11 registers)
0x47f30404:   [0x9238c000 + 0x80] = 0x309a
              [0x9238c000 + 0x88] = 0
              [0x9238c000 + 0xcc] = 1
tail:         [0x923a0000 + 0x10] = 0
              [0x923a0000 + 0x14] = 0
```

`PP+0x00 = 2` is the self-clearing command that made the block look read-only in
rounds 72/73/83: writing 1 does nothing, writing 2 is a command, and the
register always reads back its own status. My conclusion that "the PP region
ignores writes" was an artefact of writing the wrong value and then reading back.

The `0x92388000` block (11 registers) had **never been written by this driver**:

```
+0x004 = 0x000200ff   +0x188 = 0x000bf874  +0x1c0 = 0x000000ff
+0x1c4 = 0x00005555   +0x2c0 = 0x000000ff  +0x300 = 0x0000ffff
+0x304 = 62           +0x340 = 0xff5555ff  +0x344 = 62
+0x380 = 63           +0x63c = 0xaaaaaaaa
```

Also corrected: PP steering `+0x80` should be **`0x309a`**, not the `0x301a`
this driver had been writing since round 66 (that value was a *readback*, which
masks bits — round 28 even recorded "wrote 0x309a, read back 0x301a" and I then
implemented the readback).

### Result

All of the above is now implemented and runs on a cold boot
(`packet processor bring-up done`). With a freshly written rootfs: **RX still
0**, TX fine (`tx_packets=16`).

So this branch was genuinely missing but is not sufficient on its own. The
important outcome is methodological: static decoding of the call tree finds
writes that register diffing structurally cannot, and there may be further
undecoded branches — `0x47f2fd28` and the per-port chain deserve the same
treatment.


## Round 85: three more vendor writes, and two corrections

Static decoding of `0x47f2fd28` (the first call in the global init) found three
writes this driver was not making:

```
0x47f2fd68:  [0x92340000 + 0x04] = 16          TMC_CFG
0x47f2fc70:  [0x92350000 + 0x00] = (v & ~0xf0000) | 0x2f0000
0x47f303f0:  [0x9234c000 + 0x04] = 0           block never touched before
```

### Correction 1: TMC_CFG was wrongly removed

Round 81 disabled `TMC+0x04 = 16` on the grounds that it "did not appear in the
readback diff". It is plainly in the vendor code at `0x47f2fd68`. A diff cannot
see a write whose value already matches the current contents — the same blind
spot round 84 identified. Restored.

### Correction 2: the port attach mask was never actually disabled

Round 81 reported disabling the `0x921d9000+0x68` write. The edit silently
failed to match, and there is exactly one (ungated) copy in the source — the
write has been running the whole time. The round-81 claim was wrong; the
behaviour was unchanged.

### Board state: the on-flash rootfs keeps degrading

Several boots this round failed in userspace (`/etc/preinit: uci: No error
information`, then an unresponsive shell, then a panic) **with zero SQUASHFS
read errors**, so the filesystem was readable but its contents were wrong.
Reflashing the rootfs restores normal boot every time.

This is consistent with cumulative NAND wear: this driver writes with **no ECC
and no bad-block management**, and the rootfs blocks have now been erased and
rewritten dozens of times during this bring-up. Worth remembering when
interpreting a failed boot — check for a corrupt rootfs before blaming a code
change. A bisection this round wrongly implicated two new register writes for
exactly this reason; they were exonerated and re-enabled.

Current state after reflash: boots cleanly, 0 SQUASHFS errors, 9 MTD
partitions, TX works, cold-boot RX still 0.


## Round 86: external review, and two things finally settled

### A4 settled: eth_init alone arms RX (no receive required)

A red-team review pointed out that round 74's experiment was confounded: `ping`
runs `eth_init` **and then completes an ARP exchange**, so "it is not about
traffic" was asserted, not shown. Retested by pinging a **non-existent host**, so
`eth_init` runs but no exchange completes:

```
=> ping 192.168.1.55
ping failed; host 192.168.1.55 is not alive
=> nand read 0x42000000 0x700000 0x300000
=> bootm 0x42000020
root@OpenWrt:~# ping -c 4 192.168.1.100
4 packets transmitted, 4 packets received, 0% packet loss
```

`eth_init` **alone** arms the receive path. The "first received frame primes RX"
alternative is eliminated.

### Corrections forced by the review

- **"We reproduce every register eth_init writes" was overclaimed.** It rests on
  readback diffs, which round 84 proved blind to write-only/self-clearing
  registers. The static enumeration of the `eth_init` call tree is still
  incomplete (`0x47f2fb9c`, `0x47f2f800`, `0x47f2f918` not fully enumerated).
- **"Blocks eth_init does not touch" is equally weak** for the same reason —
  "0 registers changed" cannot detect a write-only trigger. The switch
  (`sw@92300000`) and PON (`pon@92000000`) blocks remain uncharacterised.
- **The rootfs-failure cause was asserted, not established.** "NAND wear" was
  never plausible (these parts are rated for thousands of cycles and we have
  done dozens). The overlay (`rootfs_data`, which lives in the tail of the
  `rootfs` partition) is the likely culprit, but no JFFS2 errors have ever been
  logged, so it is still unproven. Next failure: capture `mount`,
  `dmesg | grep -i jffs2` and `ls /overlay /etc/config` **before** reflashing.
- Note: erasing only `0xd00000..0x1720000` to clear the overlay **invalidates
  the rootfs CRC in the header** and the bootloader falls back to bank B (the
  board came up in stock firmware, `H199A V9.1 login:`). Do not do that.

### The strongest lead yet: switch CPU-port receive enable

Independent research into comparable SoCs (Lantiq VRX200/GSWIP, MediaTek
MT7530/MT7531, Broadcom b53/bcm_sf2, Realtek rtl83xx, Marvell Prestera) shows a
consistent mechanism, and Lantiq VRX200 is the closest architectural match to
this chip (switch -> PMAC -> FDMA descriptor ring, packet processor, buffer
manager):

- `gswip_port_enable()` sets `GSWIP_FDMA_PCTRLp(port) |= EN` — commented in
  mainline as *"enable port fetch/store dma"*. **Without it the MAC counts
  frames and nothing ever reaches the CPU DMA ring** — exactly our signature.
- Plus a forwarding/trap mask that must include the CPU port
  (`GSWIP_PCE_PMAP1/2/3`, MT7530 `MT753X_MFC.CPU_EN`/`MT7531_CPU_PMAP`, b53
  flood masks, rtl83xx `TRAP_SWITCH_MAC_CTRL = 2` "trap to CPU").

Our `sw@92300000` has **never been examined** — round 32 mistook it for a fifth
MAC port and round 79 only checked that `eth_init` produces no readback change
there. A write-only "CPU port receive enable" in that block would be invisible
to every measurement taken so far and would explain the entire failure.

Also confirmed by the research: no public port of this SoC family has ever got
LAN Ethernet working, and no `tm_128s.ko`/`ffe.ko`/`switch.ko` analysis exists
publicly.


## Round 88: FLASH-BOOT RX WORKS

Cold boot from NAND, no bootloader `eth_init`, no TFTP:

```
root@OpenWrt:~# ping -c 5 -W 2 192.168.1.100
5 packets transmitted, 5 packets received, 0% packet loss
round-trip min/avg/max = 31.279/175.585/511.924 ms
eth0: rx_bytes=1195 rx_packets=9  tx_bytes=2126 tx_packets=17
```

This closes the defect that has been open since round 41. The device now boots
OpenWrt from its own flash and has a working Ethernet interface with no
bootloader assistance and no workaround.

### What actually fixed it

Not one register — a sequence of blocks that were never being brought up,
recovered by **statically decoding the `eth_init` call tree** rather than
diffing registers (register diffs are blind to write-only and self-clearing
registers, which is what most of these are):

- **Round 84** — `0x47f304b0`, an entire branch never decoded:
  `PP+0x00 = 2` (a self-clearing *command*, which is why the block looked
  read-only for ten rounds), the 11-register `0x92388000` configuration, and PP
  steering with the correct `0x309a` (we had been writing back a masked
  *readback* value, `0x301a`).
- **Round 85** — `TMC+0x04 = 16` (wrongly removed in round 81),
  `TMQ+0x00 = (v & ~0xf0000) | 0x2f0000`, and `0x9234c000+0x04 = 0`.
- **Round 87** — the complete NPP bring-up from `0x47f308c4`, including
  **`[0x921cc000] = 17`** (the NPP node's second register range, never written
  by this driver) and the per-port `0x921c0060 + port*4` mask clears. This block
  had been *disabled* in round 81 on the strength of a readback diff.

### The methodological lesson

Rounds 44-83 tried to solve this by diffing registers before and after
`eth_init` and matching values. That approach could never have worked: the
writes that mattered are invisible to it. The switch to static disassembly of
the whole call tree found real missing writes in three consecutive rounds and
then fixed the bug.

### Still open

Boot reliability. The very next cold boot failed in userspace again
(`mount_root: No error information`) with zero SquashFS errors — the silent NAND
read corruption documented in docs/NAND.md round 87. Bypassing the driver's page
cache (tested this round) does **not** fix it, so a stale cache entry is not the
cause. This is now the top defect: it intermittently masks everything else.


## Round 90: scheduled review — claims hardened, and a 20x latency bug fixed

The red-team review judged both round-88 and round-89 claims overstated. It was
right, and the corrections are recorded here.

### RX: evidence strengthened (and the earlier claim was thin)

Round 88 rested on a single 5/5 ping. The reviewer noted the follow-up run showed
20% loss with a 1476 ms max RTT and that this should have been chased rather than
filed under "known latency". Retested properly on a cold flash boot:

```
ip link set eth0 down; ip link set eth0 up   -> RX returns
ping -c 60                                    -> 60/60, 0% packet loss
```

So RX survives an interface down/up cycle and is stable under sustained load.
The early-packet loss was confined to ARP warm-up. This is now reasonable
evidence; the single-ping version was not.

### The latency was a real bug, not a design limit

`avg 174 ms` against a "1 ms poll" never made sense. The cause:

```c
mod_timer(&ze->rx_timer, jiffies + msecs_to_jiffies(1));
```

With `CONFIG_HZ=100`, `msecs_to_jiffies(1)` rounds up to **one jiffy = 10 ms**.
The 1 ms poll has been a 10 ms poll since it was written. Replaced with an
hrtimer:

| | min | avg | max | loss |
|---|---|---|---|---|
| 10 ms poll | 27.2 ms | 173.7 ms | 315.2 ms | 0% |
| true 1 ms poll | **0.344 ms** | **8.88 ms** | **19.3 ms** | 0% |

A ~20x improvement. Ethernet is now genuinely usable rather than merely
functional. Decoding the `pon` RX interrupt remains the proper fix, but this
removes most of the pain.

### Scope corrections the review forced

- **"Boot reliability is fixed" was overstated.** Four clean boots against a
  ~50% failure rate is ~94% confidence, not proof; seven would be needed for
  ~99%. And `boot1` of those four still logged 5 SQUASHFS errors, which the
  stale-cache mechanism does not explain.
- **There are three distinct corruption mechanisms on record**, not one:
  (a) stale chip cache — mitigated in round 89; (b) genuinely non-deterministic
  reads (three reads, three different md5s — a stale cache is deterministic, so
  this is a different fault); (c) SMP FIFO underrun (rounds 62-63), which scales
  with CPU count and is untouched. Only (a) has a fix. Any claim of "reliability
  fixed" must be scoped to single-CPU cold boot.
- The round-89 fix is a **mitigation**: it detects "same stale page twice" and
  retries. It does not explain why the `PAGE READ` trigger sometimes fails to
  take effect.


## Round 91: timer hypothesis refuted, and a sharp new signal

### The hrtimer was not causing the boot failures

Round 90's 7-boot series (2 failures) used a new 1 ms hard hrtimer, where the
round-89 series (0 failures in 4) used the jiffies timer, so the hrtimer was a
plausible suspect. Tested by moving it to softirq context:

| timer | boots clean | ping avg RTT |
|---|---|---|
| jiffies (round 89) | 4/4 | 174 ms |
| hard hrtimer (round 90) | 5/7 | 8.9 ms (TFTP boot) |
| soft hrtimer (round 91) | 3/4 | 267 ms |
| hard hrtimer (round 91) | 2/3 | 264-381 ms (flash boot) |

Failures occur at a similar rate in every configuration. **The timer is not the
cause.** Reverted to hard mode (best latency).

Also corrected a wrong inference of my own: I initially attributed soft mode's
267 ms to softirq starvation caused by the NAND driver. That is not it — a soft
hrtimer runs from the timer softirq, which is tick-granular, and `HZ=100` here,
so ~10 ms granularity is expected. The spifc driver polls with
`readl_poll_timeout()`, which sleeps; it does not spin.

### New signal: our cold init gives a 40x slower RX path

Same kernel, same driver, two datapath initialisations:

| datapath brought up by | min | avg | max |
|---|---|---|---|
| bootloader `eth_init` (TFTP boot) | 0.52 ms | **7.07 ms** | 18.9 ms |
| our cold init (flash boot) | ~2-6 ms | **264-381 ms** | ~1030-1130 ms |

Both deliver every packet (0% loss), so this is not a reliability difference —
it is a **latency** difference of roughly 40x, and it is a much sharper
diagnostic than "works / does not work". Something in our initialisation still
differs from `eth_init` in a way that delays descriptor delivery: candidates are
interrupt/coalescing configuration, a queue depth or threshold, or the RX ring
producer being serviced differently.

This gives a continuous metric to optimise against instead of a binary one, and
it says plainly that the round-88 "RX is fixed" claim, while true in the sense
that packets flow, still hides a real gap in the init.


## Round 92: latency gap not closed; one hypothesis tested and reverted

### Ring position is not the cause

Dumping the RX ring on a cold flash boot after traffic:

```
RXRING 0 00000191 00090000 20007800 000000f0    <- fresh (len 0xf0>>2 = 60)
RXRING 1 00000191 98090000 2000780e 00000000    <- consumed (driver zeroes len)
RXRING 2 0000019e 9c090000 2000c40e 00040000    <- consumed
RXRING 3 0000019e a2090000 2000c40e 00040000    <- consumed
```

Descriptors land at slots 0-3 with the correct ownership byte, exactly as they
do after `eth_init` (round 80). So the hardware is writing to the same place and
the driver is consuming them correctly; the 40x latency gap is **not** a ring
placement or cursor problem.

### Raising the scan window is actively harmful

Hypothesis: the cursor re-walks consumed slots, so a wider scan would find new
descriptors sooner. Raising the per-poll window from 64 to 256 slots made the
board **fail to bring up the datapath at all** - two consecutive boots showed
cold TMC values (`50008000 50009000 52009000 54009000`), `Link is Down`, and an
unresponsive console.

256 uncached ring reads every 1 ms is four times the bus traffic, and it
reproduces exactly the starvation that forced this bound in round 46. Reverted
to 64 with a comment recording the result, so it is not tried a third time.

### Where the latency gap stands

Unexplained. Known: same kernel, same driver, same descriptor placement, same
consumption path; only the datapath initialisation differs, and the difference
is ~7 ms versus ~264 ms average RTT. Remaining candidates are hardware-side
delivery settings - coalescing/threshold registers, or a queue service rate -
rather than anything in the driver's RX loop.

Note this round was measured on an unstable base: two of the boot attempts hit
the outstanding ~25% NAND failure rate, which makes any single measurement
unreliable. Fixing the NAND corruption should come before further latency work,
because right now every experiment needs several attempts to get one valid data
point.


## Round 96: the boot failures were OUR OWN datapath init, and they are fixed

### Root cause

Round 79 deferred `zx_eth_datapath_init()` from probe to the first PHY link-up,
to match the bootloader's ordering. It did not improve RX (round 79 measured
that), and it turned out to be actively harmful.

Link-up timing follows PHY autonegotiation, so the init landed anywhere between
~27 s and ~65 s. `preinit` reaches `mount_root` at ~27 s. When the two collided,
userspace binaries failed to exec. The correlation across nine recorded boots was
**9/9**:

| datapath init ran at | outcome |
|---|---|
| never (TFTP boots - bootloader had already initialised) | ok |
| **26.7 / 27.1 / 28.1 s** | **FAIL** |
| 55.5 / 56.0 / 64.9 s | ok |

Side-by-side:

```
FAILING:  [11.576] Run /sbin/init as init process
          [27.108] zx-eth: npp bring-up done
                   /etc/preinit: line 37: mount_root: No error information

WORKING:  [11.468] Run /sbin/init as init process
          [27.274] mount_root: ... using tmpfs overlay
          [55.527] zx-eth: npp bring-up done
```

The init does a datapath reset (`0x92000008` cleared for 10 ms), two more
mdelays, 2048 buffer-manager writes and a 384-iteration queue loop. Running all
of that while userspace is paging binaries in is what corrupted them.

### Fix

Run the init at **probe** again, where it completes at a deterministic 11.35 s -
before `init` is even started at ~11.5 s, so it cannot collide with userspace.

### Result

Six consecutive cold boots:

```
boot1 shell=ok preinit_fail=0 ping 0%     boot4 shell=ok preinit_fail=0 ping 0%
boot2 shell=ok preinit_fail=0 ping 25%    boot5 shell=ok preinit_fail=0 ping 16%
boot3 shell=ok preinit_fail=0 ping 25%    boot6 shell=ok preinit_fail=0 ping 0%
```

**0/6 failures**, against ~25-50% before (5/7 and 2/4 in earlier series). The
residual ping loss is first-packet ARP warm-up. Against a 25% base rate, six
clean boots is ~82% confidence; against 50%, ~98%. Worth re-confirming over a
longer series, but the mechanism is understood and the init timing is now
deterministic rather than racing.

### What this cost

Rounds 89-95 were spent on the NAND read path because the symptom looked
filesystem-adjacent. The decisive evidence - the datapath-init timestamp sitting
next to the preinit failure in every log - was present the entire time. The
health counters added in round 95 pointed away from NAND immediately
(`fail=0` on the failing boot, and *fewer* read anomalies than a working one),
and that should have been enough to redirect without a review.


## Round 135: the Ethernet driver is NOT SMP-safe (blocks maxcpus removal)

Reviewed while considering dropping `maxcpus=1`. `zx_bm_alloc()` is an unlocked
multi-step handshake against a **shared** hardware buffer manager:

```c
writel(1, ze->bm + BM_REQUEST);
    poll readl(ze->bm + BM_REQUEST);
    v = readl(ze->bm + BM_ALLOC_IDX);
writel(0, ze->bm + BM_REQUEST);
```

Today `ndo_start_xmit` is serialised against itself by the netdev TX lock, and
NAPI against itself by the NAPI state machine - but **TX and NAPI are serialised
against each other only by there being a single CPU**. With the second core
running, a TX allocation and an RX refill can drive `BM_REQUEST` concurrently,
read the same `BM_ALLOC_IDX`, and hand the same buffer to two paths - or one can
clear `BM_REQUEST` in the middle of the other's handshake. `ze->sw_free_credit`
is likewise a plain non-atomic read-modify-write in `zx_bm_free()`.

The failure mode is intermittent packet corruption and ring desync, and the soak
harness would not see it - it only pings.

**Required before enabling SMP:** a `spinlock_t` (irqsave, since `zx_bm_free()`
can run in softirq) around the whole alloc handshake and around the credit
update.

What does NOT need changing: the DMA buffers are `devm_ioremap_wc` (Normal
Non-Cacheable), so there is no L1/L2 coherency exposure on the A9/L2C-310 and no
`dma_sync` requirement; the existing `wmb()` before the doorbell and `rmb()`
after descriptor reads are the correct barriers; `readl`/`writel` carry their own
barriers. PCIe touches nothing after probe.

`maxcpus=1` therefore stays for now. A test boot without it came up with a single
CPU anyway (`/proc/cpuinfo` shows one processor), so the secondary-core bring-up
in `arch/arm/mach-zx279128` has still never executed on hardware - that, not
driver races, is the first thing to debug when SMP is attempted properly.


## Round 140: buffer-manager handshake is now locked

Implemented the fix identified in round 135. `zx_bm_alloc()` drives a multi-step
handshake against a **shared** hardware buffer manager (request -> poll ->
read index -> release), and `zx_bm_free()` does a non-atomic read-modify-write on
`sw_free_credit`. `ndo_start_xmit` is serialised against itself by the netdev TX
lock and NAPI against itself by the NAPI state machine, but TX and NAPI were
serialised against **each other** only by the kernel booting with `maxcpus=1`.

Both are now covered by a `spinlock_t bm_lock` taken `irqsave` (`zx_bm_free()`
can run in softirq context).

Verified on hardware after the change: 6/6 ICMP replies, 0% loss,
min/avg/max 5.8/12.7/22.6 ms, and no lock warnings in dmesg.

This removes **one** driver-side blocker for SMP - not the only one. spifc's
cross-`exec_op` state (`prog_pending`, `prog_row`, `pos`, `pagebuf`,
`cache_valid`) is still protected only by `nand_get_device()`, a lock this driver
does not own; under SMP that dependency becomes load-bearing. Note it does not make SMP
work: a test boot without `maxcpus=1` came up single-CPU, so the secondary-core
bring-up in `arch/arm/mach-zx279128` has still never executed on hardware, and
that is the next thing to debug if SMP is attempted.


## Round 145: Ethernet does NOT carry bulk traffic - correction to "complete"

Trying to copy the sysupgrade image onto the device exposed a limitation that
every previous Ethernet test had missed, because every previous test was `ping`.

### What works

- ICMP at any size: `-s 56` and `-s 1400` both 0% loss, 3.7-14.5 ms.
- TCP connection establishment and small exchanges. Captured on the host with
  `tcpdump` while the device ran `wget`:

```
192.168.1.1.55690 > 192.168.1.100.8099: Flags [S]      seq 789653652
192.168.1.100.8099 > 192.168.1.1.55690: Flags [S.]     seq 1510405917, ack ...
192.168.1.1.55690 > 192.168.1.100.8099: Flags [.]      ack 1
192.168.1.1.55690 > 192.168.1.100.8099: Flags [P.]     length 51   (HTTP request)
192.168.1.100.8099 > 192.168.1.1.55690: Flags [.]      ack 52
192.168.1.100.8099 > 192.168.1.1.55690: Flags [P.]     length 199  (HTTP response)
```

So routing, ARP, the firewall, dropbear (`0.0.0.0:22 LISTEN`) and the TCP stack
are all fine, in both directions.

### What does not work

**Any bulk transfer stalls.** `wget` of a **4 KiB** file times out, as does 1 MiB
and the 17 MB sysupgrade image. The connection is established and the request is
sent; the transfer never completes.

Since single large frames (1400-byte ping) are fine and single small frames are
fine, the failure is not size and not connectivity - it is **sustained/bursty
receive**. That is consistent with how RX is driven: a **1 ms hrtimer poll** with
a **64-slot bounded ring scan** and no RX interrupt (none has ever been decoded).
A burst of back-to-back frames can overrun that window.

### Correction to the record

"Ethernet - complete, the only item with repeated, varied verification" was
**wrong**, and so was every reviewer ranking that rested on it. All of that
evidence was ICMP: 0% loss, RTT figures, ifdown/ifup survival, 8/8 soak boots.
None of it moved more than a few hundred bytes at a time.

**No throughput has ever been measured on this port, on any interface.** The
Wi-Fi figure (433 Mbit/s) is a negotiated link rate, and the Ethernet figures are
ping RTTs.

### Consequence

sysupgrade cannot be tested over the network until this is fixed - which is why
it is still untested. The image has to reach the device somehow, and every
in-band path (HTTP, scp) depends on bulk transfer.


## Round 146: the RX stall is not the scan window

Measured during a stalled 1 MiB download:

```
RX bytes  16413 -> 16739   (326 bytes in 12 s)
rx_packets   12 -> 17      (5 packets in 12 s)
errors 0   dropped 0   overruns 0   frame 0
```

So the driver is not discarding frames - it never sees them. The host is
sending: `tcpdump` shows the handshake, the request, and the response leaving.

### Hypothesis tested and rejected

The ring is 1024 slots and the per-poll scan window was a fixed 64, so a full
sweep took 16 polls (~16 ms). That looked like a plausible cause: a burst written
outside the current window would not be found for a long time, which fits "single
frames fine, bursts stall".

Made the window adaptive - 64 while idle (round 92 showed a fixed 256 breaks
bring-up, because 4x the uncached ring traffic every 1 ms starves the datapath
before the link is up), widening to 256 once a poll has already produced a
packet, since by then the link is definitionally up.

**No improvement**: the 1 MiB fetch still times out. So the frames are not merely being found late.

**(Round 147 correction: the second half of that sentence was unsupported - the
RX producer index had never been sampled. See below.)**

### What that leaves

- The hardware's RX free-buffer pool may be exhausted. The driver does call
  `zx_bm_free()` for every frame (including error and drop paths), but the
  vendor's buffer manager may require more than a `BM_FREE` write - e.g. a
  replenish doorbell, or a credit protocol we only partly reproduce
  (`sw_free_credit` is reverse-engineered).
- There may be a second RX ring, or a producer index register we never read, so
  the hardware writes somewhere we do not look once its own pointer moves past
  the region we discovered.
- No RX interrupt has ever been decoded; everything is polled. If the hardware
  expects an acknowledgement that only the ISR path issues, it could stop after
  a few frames.

### Honest status

This is unresolved, and it means **the port cannot move bulk data over
Ethernet**. Everything demonstrated so far - ping, TCP handshakes, 8/8 soak
boots - fits within the handful of frames the driver does receive.


## Round 147: the driver consumes everything the hardware produces - the stack drops it

### The producer index, which was in the driver all along

`TMQ_RXPROD 0x170` is defined in this driver, read **once** at datapath init, and
never used again; `rx_consumed`/`ring_synced` are assigned and never read;
`TMQ_RXCOUNT 0x11c` is defined and never accessed. `/proc/zx_eth_regs` has been
dumping all of it the whole time. Sampled across a stalled transfer:

```
BEFORE:  TMQ 170 = 0x09   rx_packets =  999
DURING:  TMQ 170 = 0x10   rx_packets = 1006     (14 s of a stalled 1 MiB fetch)
```

RXPROD advanced by 7; `rx_packets` advanced by **exactly 7**. So the driver
consumes every descriptor the hardware produces, and the round-146 framing
("frames are not being written into the ring we scan") is **withdrawn**.

### Sustained RX is fine

Flood ping from the host, which the earlier ICMP tests never exercised:

| payload | result |
|---|---|
| 56 B | 296/300 replies, 1.3% loss, 78 pps |
| 500 B | 275/300, 8.3% loss |
| 1400 B | 274/300, 8.7% loss |

So the datapath handles sustained bursts of full-size frames in both directions.
(Note the duplicates - +17 and +22 - which are unexplained and worth a look.)

### Where it actually breaks

`tcpdump` on the host during a stalled `wget`:

```
host -> device: seq 11790:13238, ack 79      <- host sent ~14 KB
host -> device: seq 13238:14686, ack 79
host -> device: [P.] seq 1:206   x5          <- retransmits, exponential backoff
device -> host: [F.] seq 79, ack 1           <- device's FIN acknowledges ZERO data
```

**The device's TCP stack accepted no payload at all.** Its final ACK number is
still 1 after the host transmitted 14 KB. The host then falls back to
retransmitting the first segment, which is why RXPROD only advances a handful of
times: the low frame count is a *consequence* of the stall, not its cause.

So frames reach the driver and are handed up, but the stack discards them -
silently, which is consistent with `rx_errors=0`. The most likely candidates are
a wrong length taken from the descriptor (checksum then fails) or payload copied
from the wrong offset.

### Next

- Compare the bytes the driver copies against what the host sent - dump the first
  64 bytes of a received frame and diff against `tcpdump -X`.
- Check `/proc/net/snmp` `Tcp: InCsumErrors` (the earlier attempt mangled the awk
  quoting over the serial console; read the raw line instead).
- Research (`zx279128s-rx-stall-research.md`) notes the descriptor status byte may
  encode a BM pool id or size class rather than a fixed `0x20`, and that
  `(BM_FREECNT >> 3) & 0x3f` looks like a byte-offset pointer being misread as a
  count - both worth testing.


## Round 148: not checksums, not the buffer pool - it is arrival RATE

Three hypotheses tested and eliminated this round.

### 1. Checksum errors - REJECTED

```
Tcp: 1 200 120000 -1 4 0 0 0 0 16 20 1 0 0 0
     ...                        InSegs=16 OutSegs=20 Retrans=1 InErrs=0 InCsumErrors=0
```

`InCsumErrors=0`, and only **16 TCP segments were ever delivered to the stack**.
The data was not corrupted on the way up - it never arrived.

(Note: an earlier attempt to read this used `grep -A1 '^Tcp:'`, which matches both
the header AND the values line, so it printed the following `Udp:` header
instead. `grep '^Tcp:' | tail -1` is correct.)

### 2. Buffer-manager depletion - REJECTED

The BM registers are **completely static** across a stall:

```
BEFORE / DURING / AFTER:   BM 0d8 = 00006200   BM 0dc = 50000111
```

so our BM interaction is inert for RX, and buffers must come from the DDR
free-list tables (2048 entries) primed at init.

### 3. Free-list exhaustion at 2048 frames - REJECTED

If the tables were never replenished, RX would die permanently at 2048 cumulative
frames. Drove `rx_packets` from 1934 to **2837** with flood ping: 891/900 replies,
1% loss, no stall. Buffers are being recycled.

### What is left: arrival rate

The distinguishing variable is packets per second, not size and not volume:

| traffic | rate | result |
|---|---|---|
| `ping -f` 56 B | ~78 pps (RTT-bound) | 296/300 |
| `ping -f` 1400 B | ~78 pps | 274/300 |
| `ping -f` x900 | ~83 pps | 891/900 |
| TCP bulk from host | **line rate, thousands of pps** | stalls after ~7 frames |

`ping -f` is not actually a flood here - it waits for each reply, so it never
exceeds ~80 pps. TCP data arrives back-to-back. During the stalled fetch RXPROD
advanced only 7 while the host transmitted at least 10 full segments plus five
retransmits, so **frames are being dropped by the hardware before the ring** once
they arrive faster than the 1 ms poll drains them.

### Next

- Generate a *real* high-rate flood that does not wait for replies (UDP blast) and
  find the pps at which RX starts dropping. That bounds the problem quantitatively
  instead of "bulk fails".
- If the threshold is well below line rate, the fix is either a shorter poll
  interval, a larger NAPI budget per poll, or - properly - decoding the RX
  interrupt, which has never been found.


## Round 149: overload WEDGES the RX path permanently

The previous rounds framed this as "bulk transfer stalls". It is worse and more
specific than that.

### Measurement

A genuine high-rate blast (2000 x 1400 B UDP, host-side 134 k pps, so wire-limited
to ~8.6 k pps):

```
rx_packets  2839 -> 4092      (1253 of 2000 delivered, 63%)
```

So at line rate roughly a third of frames are lost - already bad. But afterwards:

```
ping -c 4               -> 100% packet loss, +4 errors
ping -s 1400/1440/1472  -> 100% packet loss   (1400 worked minutes earlier)
rx_packets              -> frozen at 4092
TMQ 170 (RXPROD)        -> stuck at 0x21
ifconfig eth0 down/up   -> does NOT recover
```

**RX is permanently dead until a reboot.** The overload does not merely drop
frames; it wedges the receive path in a hardware state our `ndo_open`/`ndo_stop`
does not clear.

### This explains everything seen since round 145

A TCP bulk transfer begins, the first burst arrives at line rate, RX wedges
within a few frames, and nothing is received again - hence `InSegs=16`, the
device's FIN carrying `ack 1`, and RXPROD advancing only 7. Every "it stalls"
observation was this wedge. ICMP at ~80 pps never reaches the threshold, which is
why ping always looked healthy, including in the 8/8 soak.

### Register clue

`TMQ 160` appears to embed the producer index in bits 8-15:

```
TMQ 160 = 0x1a110900   TMQ 170 = 0x09
TMQ 160 = 0x32221000   TMQ 170 = 0x10
TMQ 160 = 0x7d5c2100   TMQ 170 = 0x21
```

The byte at bits 8-15 tracks RXPROD exactly, and the upper bytes advance faster -
plausibly a second (consumer or fill) pointer and a counter. Decoding this
register is likely the shortest path to both the drop and the wedge.

### Consequences

- **The Ethernet driver is not usable for real traffic**, and this is a defect
  a user would hit immediately.
- The soak harness would not catch it: its ICMP check passes on a wedged-then-
  rebooted device, and it never generates load.
- sysupgrade over the network remains impossible.

### Next

1. Snapshot the whole TMQ/TMC/BM windows immediately after a wedge and diff
   against a healthy boot - the difference is the stuck state.
2. Find what clears it: try re-running `zx_eth_datapath_init()` from a debug hook
   rather than `ifconfig up`, since the wedge survives the latter.
3. Only then consider whether a shorter poll or a real RX interrupt avoids
   reaching the state at all.


## Round 150: the permanent RX wedge is FIXED (bulk transfer still is not)

### The wedged state showed a backlog

Captured while RX was dead:

```
TMQ 168 = 0x5c  (92)      <- hardware had produced 92
TMQ 16c = 0x52  (82)
TMQ 170 = 0x21  (33)      <- we had consumed 33, frozen
```

The hardware had run ~59 descriptors ahead and then stopped producing. That is
the shape the research predicted: in every comparable buffer-manager design
(mvneta `MVNETA_RXQ_STATUS_UPDATE_REG`, mvpp2 `MVPP2_RXQ_STATUS_UPDATE_REG`),
returning the **buffer** to the pool and returning the **descriptor slot** to the
queue are two separate register writes. This driver only ever zeroed the length
halfword in memory, which tells our own scan a slot is free but tells the
hardware nothing.

### The fix

Write the number of consumed descriptors back at the end of each poll:

```c
if (done && zx_rx_credit)
	writel(done, ze->tmq + ZX_TMQ_RXCREDIT);   /* 0x170, boot-selectable */
```

### Result: the wedge is gone

The identical 2000-packet blast that previously killed RX until a reboot:

| | before | after |
|---|---|---|
| ping after blast | **100% loss, needs reboot** | **5/5, 0% loss** |
| backlog (`168` vs `170`) | 92 vs 33, frozen | 4 vs 10, tracking |

`ifconfig down/up` could not recover the old wedge; now there is nothing to
recover from.

### What is still broken

Bulk transfer still fails: a 1 MiB `wget` times out, `rx_packets` advances only
5 in 14 s, and TCP shows `InSegs=8` with `errors=0 dropped=0`. So the device
still acknowledges no payload and the host still backs off. The wedge was one
bug; the data path evidently has another - frames reach the driver but the TCP
stack accepts nothing.

That the two are independent is itself progress: the wedge made every other
measurement unreliable, because any load large enough to test throughput also
destroyed the interface.


## Round 151-152: poll interval is the rate limiter - and a retraction

### The drop curve against rate

With the round-150 credit fix in place, UDP at 1400 B:

| arrival rate | received |
|---|---|
| 200 pps | 400/400 |
| 1000 pps | 400/400 |
| 4000 pps | **48/400 (12%)** |

Making the poll interval tunable (`zx279128_eth.rx_poll_us`) and dropping it from
1000 us to **200 us**:

| | 1 ms poll | 200 us poll |
|---|---|---|
| 4000 pps | 48/400 | **399/400** |

So the polling interval, not the ring or the buffer pool, is what bounds receive
rate. That is unsurprising in hindsight - there is still no RX interrupt, so the
only thing pulling frames out is this timer.

### Bulk TCP still fails, and the reason is now visible

Even at 200 us, a 1 MiB `wget` times out. The capture shows why:

```
host -> device: [P.] seq 1:206, ack 79     (205-byte payload, retransmitted 5x)
device -> host: [P.] seq 50:79, ack 1      (device's ACK never advances past 1)
```

The device receives and processes **pure ACKs** (`rx_packets` and TCP `InSegs`
advance together, 4 and 4) but never accepts the payload-bearing segment. So the
remaining defect is specific to frames carrying data, not to rate.

### RETRACTION

I recorded that "the 200 us poll hangs the device" after the console went silent
and ping went to 100% loss. **That was wrong on two counts**, both mine:

1. The host had rebooted, which killed the UART logger *and* dropped
   `192.168.1.100/24` from the interface - so there was no console capture and no
   route to the device. Once the address was restored, ping was 3/3 at 0% loss.
2. The device was not even running the 200 us build by then; it had power-cycled
   back into the flash image, whose cmdline carries no `rx_poll_us` at all.

Nothing about the 200 us interval is implicated. The lesson is the familiar one
in a new costume: **before concluding the DUT failed, verify the measuring rig** -
logger alive, host IP present, and the DUT running the build under test.


## Round 153: three hypotheses tested, none fixes bulk TCP

### 1. GRO - ruled out, twice over

Made GRO switchable and booted with `rx_gro=0` (`netif_receive_skb` instead):
bulk still fails. Both reviewers independently pointed out my own data had
already acquitted it - `rx_packets` and TCP `InSegs` advance in lockstep, so
nothing is lost between driver and stack. Research adds the mechanism: in
`dev_gro_receive`, a `flush` sends the skb to `GRO_NORMAL`, i.e. **passed up,
not dropped**, and `inet_gro_receive` sets `flush` precisely on a length
mismatch - malformed is the one case GRO refuses to touch.

### 2. Ownership test masked - no change

The scan rejected any descriptor whose status byte was not exactly `0x20`:

```c
if ((readl(desc + 8) >> 24) != 0x20) continue;   /* no counter, no trace */
```

That constant came from **one** observation during bring-up (`w2 = 0x20008000`).
Any extra bit the hardware ORs in for some frames would drop them silently. Now
masked (`if (!(st & 0x20))`) with a per-status rejection histogram so this class
of drop can never hide again. Bulk still fails, but the instrumentation is worth
keeping.

### 3. TX/RX sharing buffer 0 - plausible, and appears to have made things worse

The driver's own comments record that `zx_bm_alloc()` always returns raw
`0x80000000` (index 0), so every TX frame is written into buffer 0 - and the RX
free list also contained 0. Research flagged this as fitting the whole symptom
set: a UDP blast works (device transmits nothing), ping works (ping-pong), pure
ACKs work (device idle), TCP payload fails (device transmits its request while
the reply arrives).

Reserved index 0 for TX by starting both free lists at 1. Result: **TCP now fails
to connect at all** ("Connection error: Connection failed" within ~1 s, instead of
stalling for the full timeout), while ICMP still works and is markedly faster
than before (1.8-2.2 ms vs 5-15 ms).

So the change altered behaviour but did not fix it, and may have regressed the
connect path. It is kept for now because the underlying aliasing is real and
documented, but it needs isolating from the other two changes before any
conclusion - all three landed in the same boot, which is exactly the mistake this
project keeps paying for.

### Honest state

Bulk TCP still does not work after ~9 rounds. What is now known with evidence:

- the permanent wedge is fixed (credit write, round 150);
- receive rate is bounded by the poll timer, not the ring or the pool (round 151);
- nothing is lost between driver and stack;
- IP and TCP report no header, checksum or discard errors;
- the fault is specific to frames carrying payload, and is not explained by size
  or rate.

Latent bug found in review and **not yet fixed**: the two free lists index
different pools (`TMC+0xf8 = 0x41400000` for list 2) while `zx_buf()` always
computes from `0x41000000`, so a frame delivered via list 2 is read from the
wrong 2 KB.


## Round 154: isolation - and two more rig artifacts

### The ownership-test hypothesis is DEAD

The rejection histogram added last round reports **zero**:

```
dmesg | grep -c "rx reject"   ->  0
```

Nothing with a non-zero length is being rejected by the status test, so masking
`0x20` changed nothing because there was nothing to change. The reviewer's
leading hypothesis - that the hardware ORs extra bits into the status byte for
some frames - is eliminated by direct measurement. The instrumentation stays;
it is now a permanent guard against that class of silent drop.

### Buffer-0 reservation: no effect (retested properly)

Made it switchable (`rx_skip0`) and tested both ways with a **verified** rig:
bulk TCP stalls identically with and without it.

### Two rig artifacts, both nearly misattributed to the device

1. Last round's "TCP now fails to CONNECT" - which I recorded as a possible
   regression from the buffer-0 change - was **a dead HTTP server on the host**.
   The process still existed, so `pgrep` said "running", but even a *local*
   `curl` returned `000`. After restarting it, the symptom returned to the
   original "Connection timed out", with or without the change.
2. Before that, the round-152 "device hang" was the host losing its IP and the
   UART logger dying after a reboot.

Two in three rounds. The rule already written after round 152 - **verify the rig
before concluding the DUT failed** - now needs to include "and verify the
*service*, not just the process": `pgrep` proves nothing, a local fetch does.

### Where this leaves the problem

Eliminated by measurement: GRO, checksums, IP-layer discards, buffer-manager
depletion, free-list exhaustion, scan window, ownership-status rejection,
buffer-0 aliasing, frame size, and (with the round-151 fix) arrival rate up to
4000 pps.

What remains, and it is now quite specific: **1400-byte UDP is received at
4000 pps, but TCP segments carrying payload are not received at all** - and the
one structural difference is that TCP requires the device to transmit ACKs
*while* receiving. Concurrent TX during RX is the last untested discriminator,
and buffer-0 sharing was only one possible mechanism for it.

Cheap next test that isolates exactly that: run the UDP blast **while** the
device is transmitting continuously (e.g. a concurrent outbound ping flood). If
UDP reception collapses under concurrent TX, the discriminator is confirmed
without involving TCP at all.


## Round 155: the DIR-842 parallel - tested, and what it teaches

The DIR-842 port (RTL8197F, a different ASIC family) hit a strikingly similar
bug, documented in `docs/M7-LARGE-FRAME-RX-WEDGE.md` of that tree:

> The SoC CPU-port RX path drops **every frame larger than ~128 bytes** while
> small frames flow perfectly... Because small frames keep flowing, `rx_packets`
> keeps incrementing, so the driver's missed-IRQ watchdog never fires - the
> partial wedge is **invisible to the existing recovery path**.

Its refined root cause was **data corruption, not loss**: large frames arrived
full-length with correct descriptors, but the CPU read DRAM *before* the
multi-burst payload DMA landed, so ~93% carried a corrupt IP header while their
L2 length and descriptor were correct.

### Tested here - and it does NOT reproduce

Added a detector that flags any frame whose ethertype is not IP/ARP/IPv6/VLAN
(a stale-payload frame would demux to nonsense) and dumps its first bytes:

```
dmesg | grep -c "rx badproto"   ->  0
```

Every frame this driver receives demuxes correctly. So our frames are not
arriving corrupt; there are simply too few of them. The DIR-842 mechanism is
eliminated for this device, and the detector stays as a cheap permanent guard.

### What the parallel *does* give us

1. **A precedent that this class is fixable**, and that the fix lived in a vendor
   *fabric-level* reset that no amount of CPU-engine re-init could substitute -
   worth remembering, since `ifconfig down/up` never cleared our wedge either
   (round 149).
2. **Watchdog blindness**: there, small frames kept `rx_packets` moving so the
   hang detector never fired. Ours has the identical blind spot, and our soak
   harness has the identical blind spot at a higher level (ICMP only).
3. **A confound list that mirrors ours almost item for item** - host interface
   losing its IPv4, a stale route, the box rebooting out of the image under test,
   and an ARP flush immediately before measuring that faked a total outage and
   "cost five build+boot cycles and produced two retracted findings". Our
   equivalents this month: host IP lost after reboot, UART logger dead, and a
   dead HTTP service that `pgrep` reported as running.
4. **`tcpdump` was blind on that driver** because its RX path bypassed the
   `ptype_all` tap. Ours uses `napi_gro_receive` too, so an absence of local
   capture would prove nothing here either - all our packet evidence has come
   from the *host* side, which is the right instinct.

### Status

Bulk TCP still fails. Eliminated by measurement so far: GRO, checksums, IP
discards, BM depletion, free-list exhaustion, scan window, ownership status,
buffer-0 aliasing, frame size, arrival rate to 4000 pps, concurrent TX during RX,
and now frame corruption.


## Round 156: the discrimination is by PROTOCOL, not size

The DIR-842 discriminator (does `rx_bytes` increment per-frame like a large frame
or a small one?) gives a different answer here than it did there, and it is the
sharpest result of this whole investigation.

During a stalled 1 MiB fetch:

```
A: bytes=4938 packets=43
B: bytes=5348 packets=49
delta: 410 bytes / 6 packets = 68 bytes per frame
```

68 B/frame is **pure-ACK size**. Not one large frame arrives. On the DIR-842 the
equivalent measurement showed ~1054 B/frame - frames arriving full-length but
corrupt. Here they do not arrive at all.

### Put together with what is already known

| traffic | frame size | arrives? |
|---|---|---|
| ICMP echo | 98 B and 1442 B | yes, 0% loss |
| **UDP datagram** | **1442 B** | **yes, 399/400 at 4000 pps** |
| TCP pure ACK | 66 B | yes |
| **TCP with payload** | **271 B** | **NEVER** |

A 1442-byte UDP frame arrives while a 271-byte TCP frame does not.

**RETRACTED (round 157).** A direct A/B refutes the protocol-discrimination
reading: a crafted **267-byte TCP frame carrying payload**, sent to a closed port,
gets an RST back **3 times out of 3** - and a same-size UDP frame gets an ICMP
unreachable, also 3/3. The device receives TCP payload frames perfectly well. The
68 B/frame average during a stalled fetch means only small frames were *being
sent* by that point (the host had backed off to retransmits), not that large TCP
frames are filtered.

That points at classification/steering rather than anything in the ring, the
buffer pool or the poll loop - all of which have now been eliminated by direct
measurement:

> GRO, TCP checksums, IP discards, buffer-manager depletion, free-list
> exhaustion, scan window, ownership status, buffer-0 aliasing, frame size,
> arrival rate to 4000 pps, concurrent TX during RX, frame corruption.

### Leading candidates (to test next)

1. **Multi-queue steering.** If the hardware hashes flows across RX rings and we
   service only the one we discovered, TCP could hash to a ring we never read
   while ICMP/UDP land on ours. `qmap[8]` and the queue config at `0x921d4000`
   are already in the driver as unexplained.
2. **A classifier or offload that discards TCP** - e.g. an internal L4 checksum
   check that drops rather than flags, mis-programmed so valid segments fail.
3. **`TMQ 0x160`**, whose upper bytes advance faster than the producer index and
   which has never been decoded.


## Round 157: every synthetic RX test now passes - the fault is TCP-session-specific

With the round-150 credit write and the 500 us poll in place:

| test | result |
|---|---|
| 267 B TCP frame with payload -> closed port | RST returned **3/3** |
| 267 B UDP frame -> closed port | ICMP unreachable **3/3** |
| 1400 B UDP, unpaced (1000 frames in 11 ms, line-rate burst) | **999/1000** |
| 400 DNS queries at 2000 pps to an OPEN port (matched RX **and** TX load) | rx 405, tx 391 |
| ping any size | 0% loss |

So raw receive is healthy at line rate, for large frames, for TCP frames, and
while transmitting simultaneously. **Yet a 1 MiB HTTP GET still times out.**

### Two corrections to my own recent work

1. **Round 156's "discrimination is by protocol" is withdrawn** (see above). The
   A/B that refutes it took one command and should have been run before writing
   the conclusion.
2. **Round 155's "concurrent TX during RX - eliminated" was an invalid test.**
   It used `ping -q -c 400 -s 1400 &`, and busybox `ping` defaults to a **1 second
   interval** - so 400 pings is a 400-second job, and the UDP blast it was meant
   to overlap lasted 0.2 s. At most one frame was transmitted during the window;
   the surplus 22 packets I counted were ~22 pings over ~30 s, i.e. ~1 pps. The
   independent variable was never applied. Redone properly this round with a
   DNS blast against an open port (every query generates a reply): **passes**, so
   the conclusion happens to stand, but the original evidence did not support it.

### Where this leaves the problem

Raw RX is exonerated by measurement. What remains is something specific to an
established TCP session: the device's ACK never advances past 1 while the host
retransmits. Since standalone TCP frames are processed (RST proves the stack sees
them), the next discriminator is direction - test **device -> host** bulk, which
exercises TX under a real congestion-window instead of RX.


## Round 157 (cont.): it was never about "bulk" - TCP data delivery is broken

Two tests reframe the whole investigation.

### Even a 5-byte file fails

```
tiny.bin  (5 bytes)   -> FAIL
t300.bin  (300 bytes) -> FAIL
small.bin (4 KiB)     -> FAIL
```

Every HTTP GET fails, at any size, while the TCP connection establishes and the
device's request reaches the server. **"Bulk transfer is broken" was a misnomer
from round 145 onward** - there is nothing bulk about a 5-byte response. Every
throughput, rate, burst, queue-depth and buffer-pool hypothesis chased since then
was aimed at a property that is not involved.

### TCP fails in both directions

- device -> host (HTTP GET): connects, sends the request, never receives the reply.
- host -> device (SSH on 22): `connect()` times out.

while, on the same interface and the same bridge:

- ICMP: 0% loss at every size, including 1442 B frames at line rate;
- UDP: 999/1000 unpaced 1400 B frames; DNS queries answered at 2000 pps;
- **crafted TCP frames to a closed port: RST returned 3/3.**

So the MAC receives TCP frames and the stack processes them well enough to emit
an RST - but no TCP *connection* can carry data in either direction.

### What that rules in and out

It is not: frame size, arrival rate, burst behaviour, buffer-pool depletion,
descriptor credits, the poll interval, GRO, checksum offload on payload frames,
TCP timestamps (tested with `tcp_timestamps=0`), corruption, or protocol
classification (a TCP frame with payload demonstrably arrives and is answered).

The remaining shape is narrow and odd: **unsolicited TCP frames are processed,
but frames belonging to an established socket are not delivered.** The next
discriminators are whether the bridge is involved (test with the IP directly on
`eth0`, no `br-lan`) and whether `conntrack`/netfilter is dropping established
flows, neither of which has been examined.


## Round 158: bridge and netfilter eliminated - and a hard cap

Both remaining cheap discriminators were tested and neither is involved:

| test | result |
|---|---|
| firewall stopped, `iptables -F`, policies ACCEPT | TCP still fails |
| `eth0` removed from `br-lan`, IP moved directly onto `eth0` | TCP still fails |

with ICMP still at 0% loss through both configurations.

### Final state of the Ethernet investigation

**Works:** ICMP at every size (line-rate bursts included), UDP (999/1000 unpaced
1400 B frames; DNS answered at 2000 pps), ARP, DHCP service, crafted TCP frames
to a closed port (RST returned 3/3), and simultaneous RX+TX at 2000 pps.

**Fails:** any TCP connection carrying data, in either direction, at any size -
including a 5-byte HTTP response.

**Eliminated by measurement** over rounds 145-158: frame size, arrival rate,
burst behaviour, buffer-manager depletion, free-list exhaustion, descriptor
credits (fixed - that one was real), scan window, ownership-status rejection,
buffer-0 TX/RX aliasing, GRO, TCP checksums, IP-layer discards, frame corruption,
protocol classification, TCP timestamps, concurrent TX during RX, netfilter, and
the bridge.

**Two real fixes came out of it**, both found by reading comparable drivers
rather than by iterating on the board:

1. the RX consume-credit write (round 150), which cured a wedge that previously
   required a reboot;
2. the poll interval (round 151), which took 4000 pps from 48/400 to 399/400.

### Why this stops here

Thirteen rounds. The remaining defect has survived every hypothesis that could be
tested without a datasheet, and the shape that is left - unsolicited TCP frames
processed, established-socket frames not delivered, with ICMP and UDP unaffected
on the same path - does not match any mechanism found in the mainline drivers
surveyed or in the DIR-842 precedent.

Both reviewers independently recommended capping this. The device is usable as an
access point for its own services (DHCP, DNS, ARP, ICMP all work over Ethernet
and Wi-Fi); what it cannot do is carry a TCP session terminating on the box. That
is a real limitation and it is recorded plainly in HANDOFF.md rather than being
worked around.


## Round 159: buffer-0 aliasing CONFIRMED structurally - but is not the cause

Review found that two of the eliminations justifying the round-158 cap were
invalid, and both corrections are accepted.

### Invalid elimination 1: the crafted-TCP test

Round 157 concluded "the device receives TCP payload frames fine" because a
crafted 267-byte TCP frame to a closed port produced a reply 3/3. That test used
a raw `IPPROTO_TCP` socket, which receives **every** TCP packet the host sees -
no source-address, port or flag check. Two of the three "replies" were 60 bytes,
and a bare RST is 40. The UDP arm *is* verifiable (269 = 20 + 8 + 241, an ICMP
port-unreachable quoting the datagram) and did pass, which makes the contrast
worse: the arm that can be verified passed, and the conclusion came from the arm
that cannot. **The round-156 protocol-discrimination retraction is therefore
unsupported**, and that hypothesis returns to untested.

### Invalid elimination 2: buffer-0 aliasing

Round 153/154 "eliminated" it by withholding index 0 from the DDR free lists.
But round 148 had already measured that **the BM registers never move**
(`BM 0dc = 50000111` before, during and after a stall) and the driver's own
comment says the allocator always returns index 0 - so the hardware does not
consume those lists, and changing them cannot change anything. Both facts were in
hand and were not connected.

### The identity dump settles the structure

```
rxdump idx=0 len=74 ...
rxdump idx=0 len=66 ...
rxdump idx=0 len=84 ...
```

**Every received frame arrives in buffer 0**, and `zx_bm_alloc()` returns 0 for
every transmit. TX and RX have shared one 2 KB buffer for the entire life of this
driver. That fits the pattern of what works and what does not: ping and DNS are
strict request/response on a single CPU (no overlap), a UDP blast to a closed
port transmits almost nothing (ICMP errors are rate-limited), while a TCP session
transmits ACKs asynchronously while data arrives.

### But steering TX away does not fix it

Added `tx_buf_idx` (default 2047) so transmits use a dedicated buffer:

```
tx_buf_idx = 2047
ping  -> 3/3, 0% loss          (TX still works, so the hardware honours the index)
wget  -> FAIL                  (unchanged)
```

So the aliasing is real and structural, and worth keeping fixed on its own
merits - but it is **not** the cause of the TCP failure. Something else is.

### Status

The round-158 cap is lifted to the extent that two eliminations were withdrawn,
but the outcome is unchanged: TCP sessions still do not carry data. The most
valuable untested question remains whether TCP works over **Wi-Fi**, which uses
an entirely separate datapath (mt76 PCIe DMA) - if it does, the fault is
localised to the ZTE MAC; if it does not, thirteen rounds were spent in the wrong
subsystem.


## Round 160: ANY TCP payload is dropped - a one-byte segment is enough

Re-ran the crafted-frame test with proper validation (check the reply's source
address, destination port, and RST flag - the round-157 version accepted any TCP
packet the host happened to see, which is why it gave a wrong answer):

```
TCP payload   0 bytes  ->  RST from device   3/3
TCP payload 213 bytes  ->  NO VALID RST      3/3
```

So the round-156 hypothesis was right and its round-157 retraction was wrong.
Then a size sweep:

```
payload   0  ->  RST
payload   1  ->  no reply
payload   2  ->  no reply
payload   4  ->  no reply
payload   8  ->  no reply
payload  16  ->  no reply
payload  32  ->  no reply
payload 213 with a deliberately BAD checksum  ->  no reply
```

**One byte of TCP payload is enough to make the frame disappear.**

Two corrections to how this was first written:

* The **bad-checksum probe proves nothing** and is struck from the evidence.
  `tcp_v4_rcv()` does not RST a segment failing `tcp_checksum_complete()` - it
  counts it in `InCsumErrors` and discards it. "No reply" is what a healthy stack
  does with a frame that arrived perfectly.
* "A 40-byte frame is delivered and a 41-byte one is not" is **arithmetically
  wrong**: Ethernet pads to a 60-byte minimum, so the 0-byte and 1-byte payload
  probes are *both* 60 bytes on the wire. The real result is stronger - two
  frames of **identical wire length**, differing only in the IP total-length
  field and one byte of content, behave differently.

### What this rules out, definitively

Every remaining "resource" explanation dies here: size, rate, bursts, buffer
pools, descriptor credits, poll intervals, queue depth, DMA races, and buffer-0
aliasing cannot distinguish a 40-byte frame from a 41-byte one by protocol. Nor
can checksum validation, since a bad checksum behaves identically.

Segments that ARE delivered: SYN, SYN-ACK, pure ACK, FIN, RST - all payload-free.
That is exactly the set of frames needed to open, acknowledge and close a
connection without moving data, which is precisely the behaviour observed since
round 145: connections establish, requests go out, replies never arrive.

### The likely mechanism

This is the signature of a **hardware classifier steering TCP data flows away
from the CPU** - almost certainly the vendor's traffic manager configured for
hardware-accelerated forwarding (NAT/session offload). Control frames go to the
host; data-bearing TCP segments are captured into an acceleration path this
driver never set up and never reads.

The DIR-842 port documents the mirror image of this: *"the gateway data plane
(HW-NAT forwarding) is unaffected - it runs in the rtl865x ASIC and never touches
the CPU-RX engine. Only traffic terminating on the box is hit."* Same
architecture, opposite symptom - there the ASIC path worked and the CPU path
broke; here the CPU path works for everything except the traffic the ASIC wants.

Concrete next step: the `qmap[8]` array and the queue configuration at
`0x921d4000` are already in this driver, unexplained, and the vendor U-Boot
sequence that programs them has never been disassembled. That is where a TCP
session-offload rule would live.


## Round 161: the NPP per-port bits are not the classifier

Round 160 established the fault is a classifier (a TCP segment with 0 bytes of
payload is delivered, one with 1 byte is not, and checksum validity is
irrelevant). The only classification-shaped field this driver touches is in the
**NPP block** ("network packet processor") at `0x921c0000`:

```c
for (port = 0; port < 4; port++)
	writel(readl(npp + 0x60 + port * 4) & ~0x3800000u, npp + 0x60 + port * 4);
```

Bits 23-25 cleared on a per-port register, on the basis of a vendor trace and
never tested. Made it tunable (`npp_port_mask`) and booted with the mask set to
**0**, leaving whatever the bootloader configured:

```
npp_port_mask=0   ->   TCP payload still not delivered (wget FAIL)
```

So those bits are not the gate. Worth keeping tunable - it is the right shape of
knob and costs nothing.

### Loose end

The `pr_info` added to dump the register's pre-write value never appeared in
`dmesg`, and neither does the pre-existing "npp bring-up done" message. Either
the NPP path is not executing (an `ZXI_MASK` gate, or the `ioremap` failing) or
the messages are being lost. **That needs checking before any further conclusion
about the NPP is drawn** - if the block never runs, this round tested nothing and
the result above is meaningless.

That is exactly the class of mistake this project has made repeatedly: concluding
from a negative result without first proving the code under test executed.


## Round 162: the classifier is CONFIRMED at the driver boundary

The previous rounds inferred the classifier from replies (or their absence).
`InSegs` is incremented at the very top of `tcp_v4_rcv()` - before the socket
lookup and before the checksum - so it is a true arrival detector, and combining
it with the driver counter maps the whole answer space in one probe.

Measured with the **firewall stopped** (`iptables -F`, INPUT ACCEPT), so
conntrack INVALID cannot be the explanation:

```
3 x TCP, 1-byte payload   ->  rx_packets 115 -> 115   (+0)
3 x UDP, 1-byte payload   ->  rx_packets 120 -> 123   (+3)
```

Same wire size, same addresses, same everything except the protocol byte. **The
UDP frames reach the driver; the TCP frames never do.** The drop is therefore
below the driver - in hardware - and it is not netfilter, not conntrack, not the
stack, and not checksum handling.

### A confound caught in the same measurement

An earlier single-probe reading showed `rx_packets +4` and `Ip:InReceives +4`
with `InSegs +0`, which looked like "dropped between IP and TCP" (i.e.
netfilter). That was **background traffic**, not the probe: repeating with three
probes and a quiet interface gives +0. Counting deltas on a live interface
without a control is worthless, and the control is what made this round
conclusive.

### Status

The hardware drops TCP segments carrying payload before they reach the driver.
Payload-free TCP (SYN, SYN-ACK, ACK, FIN, RST), ICMP and UDP all pass, at any
size up to 1442 bytes and at line rate. That is a complete and consistent
explanation of every observation since round 145, and it is now measured rather
than inferred.


## Round 163: the finding survives a properly controlled test - and two more invalid controls exposed

Three parallel reviews attacked this from different angles. Two of my controls
turned out to be fiction; the finding itself survived being re-measured properly.

### Invalid control 1: "measured with the firewall stopped"

**This image has no `iptables` at all** - it ships firewall4/nftables only
(`manifest: iptables -> 0 packages, nftables -> 1`; no iptables binary in the
staging root). So `iptables -F` and `iptables -P INPUT ACCEPT` were
"command not found", swallowed by the `2>/dev/null` I had helpfully added. The
box had also been rebooted since, so fw4 was up with its default ruleset during
the round-160/162 measurements.

### Invalid control 2: `zx_eth_datapath_init()` never ran in any TCP test

```c
if (!(readl(ze->mac ? ze->mac : ze->tmc) & 0xffff0000)) {
        zx_eth_datapath_init(ze);       /* else: skipped entirely */
```

**12/12 correlation across the boot log**: every TFTP boot skips it, only a flash
boot runs it. Every TCP test since round 145 was TFTP-booted, so the datapath
under test was the one **vendor U-Boot** left - and U-Boot's networking needs
only ARP, ICMP and UDP (TFTP), never TCP data. That is an uncomfortably good fit
to the symptom set, and **no cold boot had ever been TCP-tested**.

Tested it: cold boot, `datapath cold` = 1 and `npp bring-up` = 1 confirmed in
dmesg, so the driver's own configuration was active for the first time.
**TCP still fails.** A real finding - round 161's NPP result is void because that
code never ran - but not the cause.

### The controlled measurement

Null arm, identical frame size, identical destination port, `rx_errors` and
`rx_dropped` read alongside `rx_packets`, on the cold boot:

| arm | rx_packets | rx_errors | rx_dropped |
|---|---|---|---|
| null (6 s, no probes) | 25 -> 25 | 0 | 0 |
| 20 x **TCP** payload=100 (154 B frame) | 25 -> **29** | **0** | 0 |
| 20 x **UDP** payload=100 (154 B frame) | 29 -> **50** | **0** | 0 |

UDP: 21 of 20 (one background frame). TCP: 4 of 20, and those may themselves be
background - the noise floor is ~1 frame per window.

`rx_errors` staying at **0** is the key number reviewer 1 asked for and I had
never reported: the driver's pre-count rejection path
(`idx >= BUF_COUNT || len < 60 || len > BUF_SIZE - BUF_HDR`) is **not** firing.
So the frames are not arriving and being rejected - they are not arriving.
Payload=100 also puts the frame at 154 bytes, far from the `len < 60` boundary
that could have made a decode artifact look like a drop.

### Where this leaves it

The claim stands after being re-tested against every objection raised: TCP
segments carrying payload do not reach the driver, while identical-size UDP does,
with a measured noise floor, flat error counters, and the driver's own datapath
configuration active.


## Round 164: localised - the frames die UPSTREAM of the queue engine

`/proc/zx_eth_regs` already dumps the TMQ block, so this cost zero boots. Twenty
crafted frames per arm, payload=100 (154-byte frames), same destination port,
on the cold boot where `zx_eth_datapath_init()` actually ran.

**TCP arm** - every register identical before and after:

```
TMQ 150 00004b4b   ->  00004b4b
TMQ 158 00000123   ->  00000123
TMQ 15c 00007777   ->  00007777
TMQ 160 46004600   ->  46004600
TMQ 170 00000046   ->  00000046
```

**UDP control arm** - the same registers, same window, same count:

```
TMQ 150 00004c4c   ->  00005a5a
TMQ 158 00000131   ->  0000016d
TMQ 15c 00007777   ->  00007777
TMQ 160 4b004b00   ->  5f005f00
TMQ 170 0000004b   ->  0000005f      (0x4b -> 0x5f = +20 exactly)
```

`TMQ 0x170` advances by **exactly 20** for 20 UDP frames and by **0** for 20 TCP
frames. The instrument demonstrably fires, which is the check this project has
repeatedly skipped, and it fires for one protocol and not the other.

### What this pins down

The frames are not being queued and missed, not being rejected by the driver
(`rx_errors` = 0), and not being dropped by the stack. **They never reach the
queue engine at all**, so the decision is made in the classifier/parser stage
ahead of it - the NPP block (`0x921c0000`/`0x921cc000`) or the MAC's own
filtering.

Also decoded along the way: `TMQ 0x160` carries the same counter as `0x170`
duplicated into both 16-bit halves (`0x4b004b00` alongside `0x170 = 0x4b`), so it
is not a second per-queue producer index - one earlier hypothesis retired.

### Next

The NPP is now the only remaining place the decision can be made, and round 161's
attempt to test it was void because `zx_eth_datapath_init()` never ran on a TFTP
boot. Re-testing the NPP knobs **on a cold boot**, where that code executes, is
the one Ethernet experiment still worth running.


## Round 165: the SPA register is real - but the flags mask alone is not the gate

Research located a mainline driver for the sister SoC ZX279133
(`research/ZX279133-SIBLING-DRIVER.md`), which contains
`spa_set_tcp_ctrl_mask(7)` at NPPT `0x8000` bits [19:12] - an 8-bit mask over the
TCP flags byte deciding which segments are trapped to the CPU exception flow
rather than swallowed by the hardware forwarding flow.

Predicted address on our SoC: `0x921c0000 + 0x8000`. It is there:

```
[921c8000] = 03c36766        bits[19:12] = 0x36
```

`0x36` is a plausible flags mask - SYN|RST|ACK|URG under the standard bit order -
the same shape as ZX279133's default of `0x7`, though a different value.

**Opening it fully does not fix TCP.** With the register set to `0x03cff766`
(bits[19:12] = 0xFF, everything else preserved), a transfer still fails. So the
mask is not the gate on its own; the reference driver's *second* gate - a
128-entry per-port PRO protocol table selecting a flow per packet type - is the
next thing to test.

### The census settles the phenomenon independently

The per-protocol counter added inside the driver:

```
census icmp=0 udp=24 tcp_bare=8 tcp_data=0
```

`tcp_data` has never left zero, while payload-free TCP and UDP both climb. This
reaches the same conclusion as all the crafted-frame work but with an instrument
immune to background traffic and to every host-side confound that invalidated
earlier measurements.

### Two tooling notes

* `/proc/zx_eth_poke` now allows read/modify/write of any datapath register at
  runtime, so candidate registers cost seconds instead of a six-minute
  build+flash+boot cycle. **Its plain-write form has a bug** - the value is
  parsed through an 8-byte scratch buffer and truncates (`03c36766 := 00003cff`).
  The `and`/`or` forms are correct; use those until fixed.
* Round 165's first flash silently wrote **garbage**: `flash-prep` had failed
  (its rootfs input was wiped by the host reboot), so TFTP fetched nothing while
  the erase still ran. The bootloader rejected the resulting header on its CRC
  and booted the stock bank - the recovery path doing exactly its job. Rebuilt
  all three parts from the build's own sysupgrade tar and reflashed with byte
  counts verified.


## Round 175: the RX wedge is back - and it is a regression I introduced

Discovered by `rig-check.sh` failing its ping test after a 17 MB TFTP fetch
timed out. The device was alive on the console with its IP, but 100% packet loss
in both directions and the in-driver census frozen at `udp=5105`.

Quantified after a reboot, unpaced 1400 B UDP:

| burst | received | state afterwards |
|---|---|---|
| 1000 | 1000/1000 | alive |
| 3000 | 1951/3000 | alive |
| 8000 | 1117/8000 | **wedged, 100% loss** |

Cumulative frames before the wedge is roughly **4000-5000**, which matches the
`udp=5105` seen when the TFTP transfer died. So the trigger is not burst size, it
is a cumulative count since boot - the signature of a resource leaking rather
than a rate limit.

### Why this is my own regression

Round 169 made two changes to buffer supply, on review advice, both sound in
isolation:

* free list 1 now fills to `BUF_COUNT - 1` (2047 entries) so the dedicated TX
  buffer is genuinely reserved;
* free list 2 is **no longer populated at all**, because its indices alias list
  1's while pointing at a second pool base (`TMC+0xf8 = 0x41400000`) that
  `zx_buf()` never reads.

Before that, the hardware had 2048 + 512 buffers; now it has 2047. Rounds 163-164
pushed thousands of frames with no wedge, so the failure tracks the change.

Note this does **not** mean disabling list 2 was wrong - a frame delivered from
pool 2 would have been read from the wrong 2 KiB and handed up as valid-looking
data, which is worse than a stall. What it means is that the buffer supply is
leaking somewhere, and the smaller pool made an existing leak reachable in a
single sustained transfer.

### Consequences to act on

* **The soak harness's new UDP check uses 500 frames**, which is comfortably
  below the threshold - it would pass on a device that wedges a few thousand
  frames later. It needs to run enough traffic to reach the failure, or it is
  certifying the wrong property again.
* **sysupgrade delivery is blocked by this**, not by TFTP: a 17 MB image is far
  more than 5000 frames.
* The `rx_credit` write from round 150 fixed a wedge at ~2000 frames; this one
  appears later, so it is either a second mechanism or the same one with a larger
  budget.


## Round 176: cumulative-count wedge (mechanism corrected in round 177)

### The `0x20` "ownership" marker is not an ownership marker

Added a counter for slots that pass the `st & 0x20` test but decode to zero
length - the silent-skip path a reviewer flagged. First reading looked damning:

```
census icmp=13 udp=91 tcp_bare=0 tcp_data=0 zerolen=19788 rej=0
```

Nearly 20,000 against 91 delivered frames. But the counter kept climbing **with
no traffic at all**:

```
idle:  zerolen=19788  ->  zerolen=779666
```

So these are **rescans**, not frames: the poll loop sweeps slots carrying `0x20`
with no length, every poll, forever. Two conclusions:

* the counter is worthless as a leak detector, and would have been reported as
  "19,788 leaked buffers" if it had been read once instead of twice;
* **`0x20` is set on essentially every slot**, so it never was an ownership bit -
  the driver has always relied entirely on the length field to find frames, and
  the round-153 work masking that test was operating on a field with no
  discriminating power.

### The wedge threshold, measured

```
cumulative rx_packets = 3069  ->  wedged, 100% loss both directions
```

Reached by repeated 8000-frame bursts; the device survived each individual burst
and died on cumulative count, exactly as a pool-exhaustion model predicts. The
buffer pool holds **2047** entries after round 169 reserved the TX index, so a
wedge a little above 2047 means buffers are being consumed and not returned - a
slow leak, not a per-burst effect.

### What this says about round 169

Before that change the hardware had 2048 + 512 buffers, because free list 2 was
populated. Those extra 512 pointed into a second pool base that `zx_buf()` never
reads, so frames delivered from them were **read from the wrong 2 KiB** - silent
corruption. Disabling list 2 was right, and it did not create the leak: it
removed the slack that was hiding it.

So the leak predates round 169 and was masked by 512 buffers that were corrupting
data whenever they were used. That is a worse bug traded for a visible one.

### Next

Find where a buffer is consumed without `zx_bm_free()`. The error path
(`idx >= BUF_COUNT || len < 60 || len > BUF_SIZE - BUF_HDR`) deliberately does
not free when the index is out of range, but `rx_errors` is 0, so that path is
not being taken. The candidates left are frames the hardware charges to the pool
that never appear in the ring at all - which would tie the leak directly to the
TCP classifier finding, since TCP-with-payload frames are exactly that.


## Round 177: the wedge is DETERMINISTIC at 3069, and neither reset clears it

### It is a ring number, not a pool number

Reproduced on a second boot, independently:

```
rx_packets = 3069  ->  wedged, both boots, same value
```

and the arithmetic is exact:

```
RING_ENTRIES     1024
usable RX slots  1023   (slot 0 is reserved for TX and skipped by the scan)
3069 / 1023   =  3.0000     <- exact
3069 / 2047   =  1.4993     <- meaningless
```

**3069 is precisely three complete traversals of the RX ring.** The round-176
framing of "buffer exhaustion" is therefore **withdrawn**: a pool model has to
explain why the device survives 2047 and dies at 3069, while a ring model reads
it directly. Supporting this, round 148 already measured `BM+0xdc` - the driver's
own free-count register - as byte-identical before, during and after a stall.
That was filed as "our BM interaction is inert"; it equally means the pool is not
what is running out.

### Neither recovery lever works

Round 149 recorded that the wedge "survives `ifconfig down/up`". That only
exercises `ndo_open`/`ndo_stop` - it never re-runs `zx_eth_datapath_init()`.
Both stronger levers have now been tested on a genuinely wedged device:

| lever | how | result |
|---|---|---|
| fabric reset alone (`0x92000008` -> 0, then all-ones) | `/proc/zx_eth_poke` | **no recovery** |
| full `zx_eth_datapath_init()` - fabric reset + free-list re-prime + queue config | `/proc/zx_eth_reinit` (added this round) | **no recovery** |

The DIR-842 port cleared a structurally identical wedge with a fabric-level
reset after CPU-engine re-init failed. **That does not transfer here** - the
equivalent reset, and everything the driver knows how to program, leaves the path
dead until a power cycle.

So a detect-and-heal watchdog is **not** available with the levers this driver
has, and anyone reaching for one should read this first. What remains untried is
resetting state the driver does *not* own: the software ring cursor is not
re-initialised by `datapath_init`, and whatever the hardware keeps per-ring
across traversals is not reachable from any register currently known.

### Also fixed: a real TX buffer leak (not the cause)

`zx_eth_xmit()` calls `zx_bm_alloc()` - a genuine hardware handshake that takes a
buffer - then discards the returned index in favour of the dedicated
`zx_tx_buf_idx`, and never frees it. One buffer leaked per transmitted frame,
introduced in round 159. It is recorded here as a **separate bug**: TX counts
near the wedge are 54-60 frames, so it cannot drain 2047 buffers, and fixing it
will not move the 3069 threshold.


## Round 178: the 3 x 1023 match was coincidence, and descriptor release is not the mechanism

### Three descriptor-release variants, one threshold

Made the consume path selectable (`rx_release`) and tested all three on hardware:

| variant | what it writes on consume | wedge at |
|---|---|---|
| 0 | length halfword only (historical) | **3069** |
| 1 | length halfword + status word at +8 | **3069** |
| 2 | the whole 16-byte descriptor zeroed | **3069** |

Identical to the frame. So the wedge does not depend on what the driver writes
back into the descriptor, which removes "the hardware needs the slot re-armed"
from the hypothesis list.

### And the ring arithmetic does not survive a size change

`3069 = 3 x 1023` looked compelling - exactly three traversals of the usable ring.
The review that produced it said plainly: *do not build a fix on this until it
reproduces*. Tested with 20-byte frames instead of 1400:

```
1400 B frames -> wedge at 3069     (3069 / 1023 = 3.0000)
  20 B frames -> wedge at 2970     (2970 / 1023 = 2.903)   rx_bytes = 184166
```

**Different counts, so it is not a fixed number of ring traversals**, and the
exact multiple was coincidence. It is also not a byte limit (184 KB vs ~4.3 MB).
What survives is only the weaker statement: the datapath dies after roughly three
thousand received frames, with a mild dependence on frame size.

Both the round-176 "buffer exhaustion" framing and the round-177 "three ring
traversals" framing are therefore **withdrawn**. What is solid: the wedge is
reproducible, cumulative rather than per-burst, unaffected by descriptor release,
and unrecoverable by either a fabric reset or a full `datapath_init`.

### Leads worth pursuing next (from research, untested here)

* **mvpp2 had this exact bug class and fixed it in mainline** (commit
  `17f9c1b63cdd`, reported by Russell King): the hardware scatters an oversize
  frame across several buffers but the driver returns only one, so the pool
  drains slowly. It survived seven years upstream - invisible in benchmarks,
  fatal in the field. A size-dependent leak rate is exactly what the 2970/3069
  difference looks like.
* **DPAA routes parser errors to a dedicated error queue** so software can still
  reclaim those buffers. If this SoC does the same, the "missing" buffers are
  sitting in a ring nobody services - which would explain `rx_errors = 0`
  precisely, and make it a pure software fix.
* **Some BM implementations keep pool state across a warm reset** (mvpp2 commit
  `9f538b415db8`), which would explain why only a power cycle recovers, without
  needing a fabric reset at all.


## Round 179: re-priming the pool does not revive it - the pool hypothesis is dead

Implemented the pattern the research recommended regardless of root cause (DPAA
and OCTEON both use a periodic top-up to an absolute target): detect a stall,
then re-offer every buffer to the hardware. Doing this continuously would be
dangerous - handing back an index the hardware still owns corrupts a live frame -
but doing it only once the path is already dead is safe, because nothing is in
flight.

```
heal: 20000 idle polls, re-priming pool (attempt 8)
heal: 20000 idle polls, re-priming pool (attempt 9)
```

Nine attempts, each writing all 2047 indices back to `BM_FREE`. **The path stayed
dead** (100% loss throughout).

So the pool is not what is exhausted. Combined with the earlier results, the
eliminated list for this wedge is now:

| hypothesis | how it was eliminated |
|---|---|
| buffer pool drained | re-priming all 2047 buffers revives nothing (this round) |
| descriptor not re-armed | all three release variants wedge identically at 3069 |
| fixed ring traversals | 20-byte frames wedge at 2970, not 3069 |
| byte-count limit | 184 KB vs ~4.3 MB at the same failure |
| recoverable by engine re-init | `ifconfig down/up`, fabric reset, and full `datapath_init` all fail |

What remains is hardware state that only a power cycle clears, and which none of
the driver's known levers touch. That is a genuine dead end with the information
available, and it is recorded as such rather than left as an open lead.

### The honest consequence

**The Ethernet datapath is usable for roughly three thousand received frames per
boot.** That is enough for DHCP, DNS, ARP, ICMP and small TFTP transfers - the
management-plane traffic the device actually needs - and not enough for a
17 MB image or any sustained transfer. Every capability claim in this repository
has been corrected to say so.


## Round 180: the first soak run on the shipped artifact, and a bogus throughput number

Flashed the recipe's own output (overlay synced first) and ran the hardened soak:

```
boot 1: FAIL shell=1 mtd=13 persist=1 phy=1 ping=0% loss udp=1356/4000 alive=1
boot 2: FAIL shell=1 mtd=13 persist=1 phy=1 ping=0% loss udp=2024/4000 alive=1
```

What this says, plainly:

* **Boot, MTD partitions, config persistence, the Wi-Fi phy and ICMP all pass**
  on the shipped image, every boot.
* **The data-plane check fails**, which is the point of adding it: 1356 and 2024
  frames delivered out of 4000, against a threshold of 2500.
* **`alive=1` both times** - the device was still responding after the run. So
  4000 frames does not reliably wedge it; the delivery ratio is the failure, not
  the wedge. That is a more useful distinction than the harness could previously
  make.

### The throughput figure it printed was impossible

The first version reported **~248 and ~377 Mbit/s on a 100 Mbit link**. It
divided bytes by the *host's* send duration, which the socket buffer absorbs
almost instantly - so it measured how fast the host could hand packets to the
kernel, not how fast the device received them.

Rewritten to measure on the device: `rx_bytes` and `/proc/uptime` are sampled on
the DUT either side of the run, so the figure is bounded by the link by
construction. A number that is impossible on its face is worth more than a
plausible wrong one - this one announced itself.


## Round 181: the harness measured nothing, and said so loudly

The rewritten soak reported `udp=0/4000` on every boot, alongside `ping=100%
packet loss` and `alive=1` in the same line - three statements that cannot all be
true. That internal contradiction is what flagged it as an instrument fault
rather than a device fault.

The bug, found by running one command by hand and looking at the log:

```
sent:     RS=$(cat /sys/class/net/eth0/statistics/rx_bytes) ...
captured: RS=$(cat /sys/class/net/eth0/statistics/rx_bytes) ...     <- the ECHO
parsed:   RS=
```

The command **assigns a shell variable on the device and never prints it**, so
the only thing that ever reached the log was the command echo, and every reading
parsed as zero. A working device was being recorded as delivering no traffic at
all.

Fixed with `echo` and a parse that requires a digit immediately after `=`, then
validated end to end before being trusted again:

```
rs=2402 ts=182.53 re=2847468 te=195.60
frames=1973  window=13.07s  throughput=1.7 Mbit/s
```

### The throughput number is a lower bound, and is labelled as one

That 13-second window is almost entirely serial-console round trips; the transfer
itself takes well under a second. So 1.7 Mbit/s understates reality by an order
of magnitude. It is recorded as `>=` and documented in the script as evidence
that the datapath moved real bytes - **not** as a performance figure. Measuring
throughput properly needs an on-device timer around the receive loop, which this
harness does not have.

This is the third measurement artifact this session that produced a confident
wrong number (the others: a dead HTTP service `pgrep` called "running", and a
host-side send-buffer timing that implied ~1 Gbit/s on a 100 Mbit link). The
pattern is consistent enough to state as a rule: **an instrument that has never
been validated against a known-good input is not evidence.**


## Round 182: five-boot soak on the shipped artifact - the real numbers

Harness validated in round 181, run against the image the recipe produces:

```
boot 1: FAIL shell=1 mtd=13 persist=1 phy=1 ping=50%  udp=2059/4000 alive=1
boot 2: FAIL shell=1 mtd=13 persist=1 phy=1 ping=50%  udp=1884/4000 alive=1
boot 3: FAIL shell=1 mtd=13 persist=1 phy=1 ping=50%  udp=1835/4000 alive=1
boot 4: FAIL shell=1 mtd=13 persist=1 phy=1 ping=50%  udp=1561/4000 alive=1
boot 5: FAIL shell=1 mtd=13 persist=1 phy=1 ping=0%   udp=1472/4000 alive=1
TOTAL: 0 passed, 5 failed of 5
```

### What is actually reliable

**5/5 on every platform check**: reaches a shell, 13 MTD partitions register,
configuration written on the previous boot survives the power cycle, the Wi-Fi
phy comes up, no SquashFS errors, no kernel panics, and the interface is still
responding after the load run.

**0/5 on the data plane**, which is the only reason these are marked FAIL.
Between 1472 and 2059 frames of 4000 arrive - 37% to 51% - and ICMP degrades to
50% loss immediately afterwards on four of five boots.

That split is the honest summary of this port: **the platform is solid and the
datapath is not**. Previous soak figures ("8/8") measured only the first half and
were read as measuring both.

### An unexplained trend worth recording

Delivery declines monotonically across the five boots: 2059, 1884, 1835, 1561,
1472. Each boot is a fresh power cycle, so nothing in the driver should carry
over. Candidates: a thermal effect, something retained in hardware across a warm
power cycle, or drift in the measurement window itself. **Not investigated** -
recorded so the next person sees the trend rather than a single number.
