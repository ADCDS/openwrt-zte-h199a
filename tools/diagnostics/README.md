# H199A PCIe diagnostics

These patches are **not applied by build.sh** and do not change the release
kernel. They preserve the private diagnostic implementation used on the bench
on 2026-11-18. Apply them only to a disposable copy of the pinned 6.6.151 kernel
whose H199A PCIe driver matches this repository.

Apply `pcie-config-trace.patch` first. It adds two optional, read-only files on
each PCIe platform device:

- `cpu_config_writes`: a 32-entry RAM ring of CPU write intentions, newest first,
  with monotonic total and per-route counts. The hooks cover DWC DBI helper
  writes and the root bridge's PCI configuration write operation, including
  standard capability registers such as PMCSR. They preserve the original
  operations and child-bus configuration path. The filter covers standard
  configuration `0x00..0xff` and AER status ranges `0x104..0x107`,
  `0x110..0x113`, `0x130..0x133`; it does not record every nonstandard DBI
  register. iATU callbacks using a different base are excluded.
- `board_controls`: all six CRM2 mux words and, on port 0, GPIO52–55 direction
  and input levels. It requests no GPIO and changes no level, direction or mux.

Enable the boolean `zte,trace-config-writes` on the private
`/soc/pcie@f000000` and `/soc/pcie@f100000` nodes. Keep the release PHY/reset
properties unchanged. Verify `enabled=1`, `dbi>0` and `pci>0` after boot; an
empty ring alone does not prove that the hooks ran. Compare totals before and
after a fault, because older entries can be overwritten or omitted from the
page-sized text view. Entries show attempted writes, not accepted hardware
values. Direct MMIO through other paths, DBI2, DMA and writes to reset/clock
controls remain outside these hooks. Silence cannot establish a board defect.

The logger performs no MMIO, allocation or printing. The sysfs reader allocates
its snapshot before taking the short IRQ-safe lock, copies metadata under the
lock, then formats and frees it afterwards. This keeps the reader's kernel
stack below the platform's 1024-byte frame limit.

`pcie-late-perst-experiment.patch` applies after the observer. It adds the
private port-0 boolean `zte,late-perst-retry`. If port 0 is still missing after
normal shared initialization, it stops and verifies both LTSSMs, asserts both
existing PERST lines for 100 ms, releases both for 200 ms, then retrains and
resamples both links. It runs once **before either PCI host is published**.
It never replays the shared CRM sequence or adds a live reset interface.
Errors attempt both releases, preserve the first error, and prevent host
publication. The helper passed 13 actual-C success/fault-injection cases. Reproduce them
without accessing a router:

```sh
python3 tools/diagnostics/check-late-perst.py
```

The check applies both patches to a temporary source copy, extracts the actual
helper and tests ordering, both-line cleanup, error precedence and prevention
of training after failed readback.

**That experiment did not recover 5 GHz on this unit.** It is retained for
reproducibility, not as a fix. The missing-link mask remained `0x1`; port 1 and
wired access remained usable. GPIO52/54 stayed low, GPIO53/55 high, all outputs,
and the six mux words matched the decoded VID6 tables exactly:

```text
0f3ffffa 00effeff 0555ffff 003dbf85 00000000 00000000
```

`pcie-rc-setup-experiment.patch` is an alternative to the late-PERST patch;
apply it after the observer. Its private port-0 property is
`zte,stop-ltssm-before-rc-setup`. For an initially down link it holds only that
port's LTSSM off while generic DWC root-complex setup runs. A control-aware
`link_up` then forces the existing `start_link` callback to enable training.
An enabled link already in L0 is left unchanged. This changes no GPIO or shared
clock/reset register and runs before that host is published.

That control also ran and failed to recover the endpoint: the callback logged
CTRL `0x00000008`, port-link control (`0x710`) `0x00010120` and width/speed
control (`0x80c`) `0x0002012c` before
re-enabling; the subsequent link wait timed out. It is another failed diagnostic
control, not a release change. Use one experimental flag at a time.

Rebuild the kernel and regenerate all image/container checksums using the
unit's own header and calibration. A direct kernel build does not update an
older sysupgrade archive. Keep a verified recovery bank; use the existing image
checks and readback procedure. Raw UART logs, headers, calibration and Wi-Fi
client configurations from the bench are private and are not included here.
