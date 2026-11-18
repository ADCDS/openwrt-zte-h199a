> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# H199A UART header — pad map & pitfalls (learned the hard way, 2026-08-20)

## The trap: one candidate pad is a BOOT STRAP

The board header exposes two adjacent candidate pads besides GND. They are
NOT equivalent:

- **Pad A (strap pin):** connecting the USB adapter's TX here holds the line
  high during ROM reset sampling → the mask ROM boots into **UART download
  mode**: prints `Boot UART` / `ROM# ` per power-cycle, never reaches cspboot,
  ignores keyboard input. Silent otherwise (no XMODEM poll bytes).
- **Pad B (true router RX):** normal boot; host TX reaches cspboot/U-Boot.

Proven experimentally: TX on pad A → ROM loop; TX disconnected → normal
stock boot; TX on pad B → full boot-mode entry to the `=> ` prompt.

## Working mapping (CP210x / CH340, 3.3 V TTL)

```
adapter TX → pad B (router RX)
adapter RX → router TX pad
GND        ↔ GND            (all THREE lines mandatory — flaky GND mimics dead TX)
```

Do **not** connect the adapter's VCC/3V3 pin anywhere (router self-powered).

## Rig scripts (workspace root, `~/dev/routers/h199a/`)

| Script | Role |
|---|---|
| `uart-log.sh` | socat RX-only logger → `logs/uart.log`, survives replug/power cycles (background) |
| `catch-bootmode-v2.sh` | state machine on the log: `Press 1`→sends `1`, password prompt→`Boot4128s!\r`, autoboot→CR; ends at `=> ` |
| `uart-send.sh` | one-shot TX (coexists with logger) |
| `tomada` | smart plug power: `tomada off/on` (mA/W metering is WRONG — trust the UART log) |

Only one TX writer at a time; the catcher and manual `uart-send.sh` calls
must not overlap. The logger (RX) can always run.

## Boot-mode entry (manual)

Power on → `*** Press 1 means entering boot mode***` (3s countdown) → send `1`
→ `*** Please input bootmode password: ***` → send `Boot4128s!` + Enter →
cspboot menu → `Hit any key to stop autoboot` → any key → `=> `.

## Serial login on stock

Stock firmware presents `H199A V9.1 / login:` on ttyAMA0 after boot —
credentials unknown (`multipro/multipro` is web-UI only). Useful as a TX
echo test (typed characters echo back).
