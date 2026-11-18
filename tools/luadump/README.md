# luadump: partial stock Lua-bytecode inspection

The inspected H199A web modules use PUC Lua 5.1 bytecode (`\x1bLuaQ`).
`lua51dump.py` is a small dependency-free inspection aid for that captured
format, not a general Lua decoder or decompiler:

```sh
python3 tools/luadump/lua51dump.py /private/stockfs/home/httpd/webmodules/modules/do_firmware_upgrade.lua
```

Obtain your own firmware files; they are not distributed here. The web upgrade
protocol is documented in [WEB-UPGRADE.md](../../docs/WEB-UPGRADE.md) and was
validated independently against the C services and hardware.

## Implemented assumptions and limits

The loader checks the Lua magic and version, then skips the remaining header.
It hard-codes little-endian 32-bit `int`, `size_t` and instruction fields with
8-byte doubles; it does not validate all layout fields or accept arbitrary
Lua 5.1 builds. Rejection by a stock `lua`/`luac` does not establish the complete
format that this parser assumes.

It displays prototypes, constants and an approximate pseudo-disassembly.
`CLOSURE` uses Bx. GETTABLE's key uses RK(C); SETTABLE uses RK(B) for the key and
RK(C) for the value. The present renderer does not implement all those operand
semantics correctly. Its jumps use unsigned Bx rather than signed sBx, and its
LOADNIL range rendering is inaccurate. Do not infer reliable control flow,
register lifetimes or complete source from that output.

Resolve important instructions from the raw bytecode and the Lua format, and
cross-check behavior against the C side (`httpd`, `cmapi`, `cspd`, flasher) and
a bounded test. The tool is preserved for historical investigation; a readable
printed line is not proof that its interpretation is correct.
