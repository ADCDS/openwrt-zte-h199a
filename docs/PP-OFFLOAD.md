# Packet-processor access and hardware flow-offload status

**Hardware per-flow offload is disabled and unqualified.** Diagnostic work
demonstrated register/table access and default-flow hardware forwarding. It
did not demonstrate a working per-flow CLA exact-match path for the GE-to-GE
traffic tested. These results do not establish that hardware offload is
impossible on the board.

The H199A exposes one GE WAN jack and three GE LAN jacks. Vendor SoC block
names and directional pipeline terminology do not imply that this board has
an optical connector. Its working routing/NAT path is Linux software forwarding.

## Release configuration

All four symbols below are unset in
`files/target/linux/armsr/config-6.6`:

| Symbol | Diagnostic or experimental function |
|---|---|
| `CONFIG_ZX279128_ETH_DEBUG` | Experimental parameters and Ethernet `/proc` controls |
| `CONFIG_ZX279128_PP_TABLES` | CLA/PM table access and backing-memory allocation |
| `CONFIG_ZX279128_PP_FLOW_TEST` | Explicit single-flow installs and measurement controls |
| `CONFIG_ZX279128_PP_OFFLOAD` | Experimental netfilter flow-table integration code |

Software flow offload is a separate firewall setting. It was enabled for the
378.7/375.7 Mbit/s wired NAT measurement; the recipe does not explicitly enable
it. The corresponding no-offload result was 360.2/307.1 Mbit/s. These short
bench tests used an earlier production image, not a fresh performance run on
the bank-aware release. See [Ethernet](ETHERNET.md) and
[Validation](../VALIDATION.md).

## What exists in the source

The implementation is under
`files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/`:

| Source | Role |
|---|---|
| `zx279128-pp.c`, `zx279128-pp.h` | Table allocation, bounded indirect access, debugfs and teardown |
| `zx279128-pp-hash.c` | Decoded window/key builders, hash selection and placement helpers |
| `zx279128-pp-flow.c` | Gated single-flow diagnostic interface |
| `zx279128-pp-offload.c` | Experimental `TC_SETUP_FT` flow-table helpers |

The netfilter helpers are not connected to the Ethernet netdev operations in
the current driver. The proposed `ndo_setup_tc`, port-index mapping and
port-down cleanup remain in `docs/offload/eth-hookup.patch`. The patch is an
unapplied development artifact, not an installation step or evidence of a
working hardware path.

With PP tables enabled in a diagnostic build, the probe requires CLA and PM
readiness and allocates 4 MiB of ACL memory plus 1 MiB of PM memory. Addresses
must be 128 KiB aligned and addressable by the 32-bit base registers. It programs
PM base `0x923a0020` before ACL base `0x923a0024`, verifies readback, and reads
the hash configuration. Indirect operations are serialized per engine, checked
against decoded bounds and stopped after a timeout; a faulted engine refuses
later operations. Teardown retains allocated memory if a live entry cannot
be cleared or a base register still points into it.

The diagnostic PP bring-up includes a TOPCRM reset at `+0x08` bits 4/5 and
clock gate at `+0x0c` bits 5–8, mask `0x1e0`. The earlier `0x1e` decode was
wrong. Those PP-table-specific operations are excluded from the release
configuration. The normal Ethernet CPU-trap selector remains UDP/TCP at
SPA `0x921d41c0`, value `0x11060000`.

## What the hardware experiments establish

Diagnostic RAM boots demonstrated programmed base-register readback, bounded
CLA/PM reads without timeout, and single-flow install/readback/delete. A
60-minute read-path observation kept the bases stable with no indirect-read
timeouts and continued software forwarding. This is partial qualification;
table teardown/unbind and production hardware offload remain unqualified.

A later test cleared the UDP soft-trap selector and configured a downstream
unicast default flow. A test frame reached the wire with Linux RX/routing
counters flat; the frame was byte-identical and reflected to the ingress jack.
Deleting the exact-match entry left that forwarding unchanged. This proves a
hardware default-flow path, not a per-flow routed or NAT offload path.

Exact-match experiments on downstream traffic, a WAN jack classified upstream,
and a physical LAN ingress produced no observed per-flow aging hits. Positive
aging-bit controls were checked. The tested states included decoded entries,
ternary extraction rules, hash-bank sprays, comparison masks and additional
SPA initialization. SPA RAM writes lacked independent array readback, which
limits conclusions about that part of the experiment. No tested combination
established working exact-match forwarding.

The fenced historical [key and bench record](PP-KEY.md) retains measurements
and withdrawals. Its diagnostic register writes are private bench experiments,
not production configuration instructions. [Flow-install design](PP-FLOW.md)
summarizes the current source without prescribing table writes on a running
release router.

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/PP-OFFLOAD-BRINGUP.md). They are not current installation instructions.
