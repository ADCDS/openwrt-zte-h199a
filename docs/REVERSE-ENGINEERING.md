# Reverse-engineering methods (reusable beyond this SoC)

This port was developed using vendor bootloader/NAND captures and a stripped
vendor kernel rather than an available SoC datasheet or matching vendor SDK. These are the
techniques that worked, written so they transfer to the next undocumented SoC
rather than living buried in journals.

## 1. Mine `__ksymtab_strings` before touching hardware

A stripped vendor `vmlinux` often still contains the exported-symbol name table
(`__ksymtab_strings`). Reading it by name recovers the vendor's entire exported
API for free — and it may be the *only* entry point you get.

Two things it recovered here:

- **SMP bring-up** (see below) — the whole `smp_operations` structure was
  located via the `CPU_METHOD_OF_DECLARE` table entry `{"zte,zx279128-smp",
  0xc059bc18}`, after ~180 rounds of assuming the mechanism was unobtainable.
- **The vendor's flow-accelerator API** (`ffe_*`, `npu_*`) — recovered by name,
  which is how the accelerator hypothesis could be tested against the binary at
  all.

How to find the table: locate a known exported string (e.g. a
`kallsyms_lookup_name` reference), then identify `__ksymtab_strings` by scanning
for runs of NUL-terminated C identifiers. The strings are the map.

## 2. Resolve ksymtab layout empirically, don't assume

Linux 4.1 ARM32 uses a classic **absolute two-word** `struct kernel_symbol
{ unsigned long value; const char *name; }` — 8 bytes, no PREL32, no namespace
field. Other kernel versions/builds may use relative offsets; inspect the actual format. Determine the layout by:

1. Find the name-string offset.
2. Look for a pointer to that string; the `value` is the word immediately
   before it.

**Trap that cost time here:** the same string can be pointed at from *two*
tables. The kallsyms table's "value" is the previous string pointer (garbage);
the real ksymtab's value is a code address. Distinguish by whether the resolved
value looks like code (ARM word-aligned, sane Thumb bit, lands inside the text
region).

**Load base:** an extracted flat ARM `Image` has no ELF header; `vmlinux`
normally names an ELF file. For a flat payload, recover the base by voting
every pointer-looking 32-bit word against valid string-start offsets — the base
with the most consistent votes wins (here 0xC0008000, 18k+ votes vs ~8k for the
runner-up; standard ARM TEXT_OFFSET). In ordinary unconditional ARM encoding,
`B` starts `0xea...` and `BL` starts `0xeb...`. An instruction alone does not
establish the container format; identify/decompress a zImage or other wrapper
first and retain the original ELF/flat distinction.

## 3. The holding-pen SMP pattern (the highest-value single result)

On dual-Cortex-A9 SoCs with no PSCI (32-bit, platform `smp_operations`), the
secondary core is often **already running** — parked in a holding pen in on-chip
IRAM by the BootROM — rather than needing a clock/reset/power sequence. This explained failed power-domain hypotheses on this unit; it is not a
general rule for other SoCs.

The pattern, recovered here:

1. The secondary polls two words in an IRAM page: `+0x04` = jump address
   (`secondary_startup`), `+0x08` = pointer to `zx_pen_release` (CPU id).
2. The kernel `ioremap`s that IRAM executable, copies a trampoline, writes the
   two words, then writes the target CPU id into the pen variable and issues
   `SEV`.
3. **No clock, reset, or power register is touched at all.**

Two bugs that blocked this for ~180 rounds, both only visible after recovering
the vendor stub from the binary:

- The vendor stub has **no `WFE`** — it is a pure poll. ARM's event register is
  one-shot, so a `SEV` issued while the core is still in the BootROM's pen is
  consumed and the core then blocks forever in a `WFE` that was never supposed to
  be there. One instruction explained "the secondary never starts".
- Outer-cache maintenance must be applied to **physical** addresses, not to an
  `ioremap`'d virtual address; and a Device (uncached) mapping needs no cache
  maintenance at all, only a barrier.

**Method:** disassemble the vendor's `smp_operations` from the stock binary (via
§1–§2), don't guess at the mechanism from register poking.

## 4. The verification discipline that kept this project honest

Repeatedly, a "confident" conclusion was wrong because the instrument could not
actually fire, or the artifact was not what was tested. These are the rules that
caught them:

- **`bytes written: OK` is not verification.** Even with production on-die
  ECC, a success message does not establish that the intended bytes landed. Verify by reading back and
  comparing — U-Boot `cmp.b <src> <readback> <len>`. A smaller "total" is the
  *offset of the first difference*, not a count of matches; `cmp.b` stops at the
  first mismatch.
- **Prove the instrument can fire before trusting a null result.** A counter
  that has never been non-zero proves nothing (the `tcp_data=0` census was only
  meaningful because the adjacent `tcp_bare` counter was non-zero, proving the
  TCP branch was live).
- **Validate the artifact, not the source.** Twice, a fix was "verified" by
  reading the source or a hand-edited build tree while the shipped recipe still
  produced the old behaviour. Sync the overlay (`cp -a files/. .`) and build
  what you flash.
- **`pgrep` proves a process exists, not that a service works.** Fetch the
  service's actual response.
- **A dmesg line that matches the shape of your hypothesis is not evidence for
  it.** Check the device identity (`lsusb`) before attributing a bus event.
- **Register semantics are not transferable by name.** This driver's own source
  contradicts itself (one register `#define`d `RXPROD` twelve lines from a
  comment calling it "consumed"); the round-150 capture named three registers
  with three distinct meanings. An elimination is only as good as the register
  semantics it rests on, and those are reverse-engineered.

## 5. Decisive measurements cost less than reverse-engineering

The accelerator hypothesis was built over ~30 rounds and refuted in two
independent ways: the register `ffe_get_npu_enable` reads turned out to be a
software flag, and the `tcp_data=0`-always census is the signature of a static
rule, not a learned-flow offload. A learned-flow offload would have let the
first N packets of each connection through at least once.

The decisive test would have been: send **exactly one** payload-bearing segment
on a fresh connection and observe whether it reaches the driver. It needs no RE
and separates "static rule" from "threshold offload" outright. **Design the
cheapest discriminating measurement before investing in reverse-engineering.**

## 6. Prove a packet's fate by where a counter sits, not by a missing reply

To answer "does a given packet class reach the CPU?", the instinct is to look for
a protocol-mandated reply - e.g. a closed TCP port must emit a RST, so "SYN in,
no RST out" looks like proof the SYN never reached the stack. **That inference is
unsafe on a real system:** a firewall (OpenWrt ships `firewall4`, default-DROP
inbound) silently eats the SYN and emits nothing, with no classifier involved.
The absence of a reply has too many causes.

The reliable method is a **counter placed upstream of everything that could
silently drop the packet.** The historical diagnostic driver incremented a per-protocol census in the
NAPI receive poll, right after `memcpy_fromio`, ~75 lines before
`netif_receive_skb` - i.e. before netfilter processes the frame. Production
disables `CONFIG_ZX279128_ETH_DEBUG`; this instrumentation must be enabled in
a separate diagnostic image before using that measurement. So `tcp_bare=0` there is
firewall-immune and genuinely proves frames never reached the driver, whereas the
missing RST proves nothing.

Two discipline points this cost real rounds to learn:

* **Know exactly where your instrument sits in the pipeline.** A counter after
  the firewall and a counter before it answer different questions; conflating
  them manufactures false confidence.
* **Control the boot path.** The same measurement gave `tcp_bare=0` on a manual
  `bootm` boot and non-zero on a `cspboot` boot. If a variable co-varies
  perfectly with your outcome and you did not control it, you have not measured
  what you think - you have measured that variable.

## 7. When a capability claim changes, sweep the whole tree for the old wording

This project corrected the same class of defect three times: a newer measurement
lands in one file, and the *conclusion sections, capability tables, and other
docs* keep asserting the superseded claim - the repository ends up arguing with
itself. Round 243 fixed six such contradictions; rounds 244-245 immediately
created three more, because the fix was manual and did not generalise.

The rule that actually prevents it: **any change to a capability claim ends with
a grep of every user-facing doc for the superseded wording**, not just the file
you edited. Concretely, before committing a capability change, grep
`README.md HANDOFF.md docs/*.md` for the old number/phrase (e.g. "100% loss",
"one-off", "37-51%", "not re-tested") and confirm zero stale hits. A headline and
its file's own tail are the two places that most often disagree - check both.
