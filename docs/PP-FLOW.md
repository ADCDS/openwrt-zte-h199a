# Experimental single-flow installation

`zx279128-pp-flow.c` is a diagnostic interface for installing one explicitly
specified IPv4 flow and reading its CLA aging bit. It is not a working
hardware acceleration feature. The tested GE-to-GE flows produced no observed
exact-match hit. Default-flow hardware forwarding was demonstrated separately;
it did not depend on an installed exact-match entry.

The release leaves `CONFIG_ZX279128_PP_FLOW_TEST` and its prerequisite
`CONFIG_ZX279128_PP_TABLES` unset. There is no production flow-control file.
In a diagnostic build, the write-only debugfs control is additionally gated
by `flow_test_enable`, initially zero. This document describes that source;
it does not prescribe register or table writes on a release router.

## Source and evidence

The files are under
`files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/`:

- `zx279128-pp.c` and `zx279128-pp.h`: indirect access, table ownership and bounds.
- `zx279128-pp-hash.c`: decoded key/window builders and hash placement helpers.
- `zx279128-pp-flow.c`: explicit installs, removal, controls and measurements.

Layouts were recovered from stock vendor modules. Host tests exercise the
actual builders and control paths, but do not simulate the packet processor.
The vendor modules, full captures and bench instruments are private evidence,
not files supplied by this repository. The fenced [PP key record](PP-KEY.md)
contains the historical decode, experiments and corrections; the current
[PP status](PP-OFFLOAD.md) states the qualification limits.

## Current decoded model

| Component | Source model |
|---|---|
| CLA window | 60 bytes; action fields and twenty 16-bit match words |
| Hash key | 45 bytes, repacked from the window |
| IPv4 fast-rule selector | `extIdx=9`, nibble 0, combined field `0x90` |
| IPv4 match words | Protocol, source/destination IPv4 addresses and TCP/UDP ports, under the selected extraction rule |
| Hash | MSB-first CRC, initial value zero, no final XOR, key bytes processed in reverse order; low 16 bits retained |
| Inner buckets | Four banks: 256, 128, 64 and 64 slots; eight additional slots at 512–519 |
| PM `flow_info` | Three words; address `(direction << 10) | index` |
| PM `next_hop` | Three words encoding destination MAC and destination IPv4 address |
| Per-flow observation | CLA aging bit; read and explicitly clear it |

The IPv4 fast-rule selector is an extraction-rule index, not an ingress-port
number. Earlier claims that the hash key was inherently per-port or that its
nibble selected ORIGINAL versus REPLY were withdrawn. The source's IPv4
builders use `rule_mode=0` and `direct=0`; those bits are not the earlier
`rule_mode=1` test encoding. Register readback of a built entry establishes
storage of the programmed representation, not that a live packet matches it.

Hash polynomial choices are read from CLA configuration rather than assumed
from reset values. The placement helper declines an undecoded external-table
configuration. Software tracks occupied entries; the aging bit is a hit
indicator, not a free-slot map or a byte counter. ADM aggregate counters do
not establish per-flow packet/byte counts.

## What the diagnostic code does

The legacy `add` path is a fixed-slot, never-matching readback control at hash
slot 519. The `addh` path builds the decoded IPv4 window and chooses a candidate
bucket. Both use reserved PM `next_hop` index 511 and `flow_info` index 1023.
The `flow_dir` parameter selects the PM address direction: zero for up, one
for down. The installed address is retained so deletion clears that same
address even if the parameter subsequently changes.

Installation writes next-hop and flow information before making the CLA entry
valid, then clears its aging bit. Deletion clears the CLA window and aging
state before clearing the referenced PM entries. Failed deletion keeps the
installed-flow record, so teardown can retain the backing memory rather than
free it under a possibly live entry. At most one explicit flow is installed.

The test interface accepts TCP/UDP IPv4 tuples and L2-forwarding information.
It refuses source-IP/source-port NAT rewriting. IPv6, VLAN, PPPoE and DNAT
are outside this interface's supported model. The parsed source-MAC argument
is advisory; it does not implement an arbitrary source-MAC rewrite.
Additional controls support extraction-rule experiments, aging positive
controls, candidate-window readback, hash-bank sprays and both upstream and
downstream pipeline-counter reads. Those controls remain diagnostic only.

## Qualification boundary

The table write/readback/delete path has hardware evidence. No tested
exact-match install demonstrated per-flow forwarding, L2 rewrite or NAT.
The successful default-flow experiment persisted after deleting the installed
flow and therefore cannot qualify it. Further work needs a reproducible
positive exact-match control and wire-level forwarding evidence, followed by
safe deletion, teardown, isolation and regression qualification. Current
negative results do not prove a permanent hardware limitation.

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/PP-FLOW-DESIGN.md). They are not current installation instructions.
