# H199A UART pads and boot-strap trap

Current guidance, **2026-11-18**. The pad distinction below was established on
the bench unit on 2026-08-20. UART is used for bootloader access and recovery;
the current stock-web installer can install from either stock bank without
UART writes. See [INSTALL-NO-UART.md](INSTALL-NO-UART.md) and
[INSTALL.md](INSTALL.md).

## Electrical connections

Use a **3.3 V TTL** USB-UART adapter at **115200 baud, 8 data bits, no parity,
1 stop bit**, without hardware flow control. CP210x and CH340 adapters were
used on the bench. The router has its own DC supply.

| Adapter connection | Router connection |
|---|---|
| TX | True router RX pad, called **pad B** in the original bench notes |
| RX | Router TX pad |
| GND | Router GND |
| VCC / 3V3 / 5V | **Leave disconnected** |

TX, RX and a reliable common ground are all needed for interactive control.
A poor ground can resemble a dead transmit path. The names “pad A” and
“pad B” distinguish the original candidate pads; they are not a numbered
connector pinout or an orientation diagram. Confirm the physical pads before
connecting an adapter, and do not infer their order from these names.

## One candidate pad selects ROM UART download

The two adjacent candidate pads besides GND were not interchangeable:

- With adapter TX connected to **pad A**, the line was held high during reset
  sampling. The mask ROM printed `Boot UART` / `ROM# ` and did not reach
  cspboot. No XMODEM polling bytes or useful interactive response appeared.
- With TX disconnected, normal stock boot resumed.
- With adapter TX connected to **pad B**, input reached cspboot and U-Boot,
  including the `=> ` prompt.

Pad A is therefore a boot-strap trap for this connection. A ROM download prompt
does not establish a firmware fault or the availability of a recovery transfer
protocol. Use the true RX pad for normal console control.

## Bootloader entry

On the tested stock boot chain:

1. At `*** Press 1 means entering boot mode***`, send `1` during the countdown.
2. At `*** Please input bootmode password: ***`, send `Boot4128s!` followed by
   Enter.
3. Continue through the cspboot menu; at `Hit any key to stop autoboot`, press
   a key to reach U-Boot's `=> ` prompt.

The boot-mode password is for this bootloader prompt, rather than the stock
web interface or Linux login. The stock Linux console presented
`H199A V9.1 / login:` on `ttyAMA0`; its login credentials were not established
by these UART checks. Successful bootloader input does not establish Linux
login access.

Use one coordinated UART reader and **one TX writer at a time**. A passive
logger can coexist with a coordinated writer, but interactive terminals and
automation must not compete for input or transmit concurrently. Do not use
a text log as the byte transport for XMODEM. Repository controllers have
specific UART-ownership, power and logging requirements; follow their own
interfaces rather than copying commands from the former private bench rig.

## Power-state limitation

Leaving the UART attached can affect an investigation of power-off or strap
state even when its VCC pin is disconnected; the actual influence on this unit
has not been measured. The current 5 GHz investigation still needs a physical
DC-plus-UART disconnect or rail/reference-clock measurements. The bench UART
and Internet adapters share an xHCI controller, and the USB2 hub reports no
power switching. No USB-port power action or controller reset was attempted.
See [WIFI.md](WIFI.md) for the measured evidence and remaining limits.

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/UART-BENCH-NOTES.md). They are not current installation instructions.
