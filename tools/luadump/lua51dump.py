#!/usr/bin/env python3
"""Minimal Lua 5.1 bytecode parser/disassembler (PUC luac format).

Used to recover stock-firmware web-module logic (LuaQ = Lua 5.1 bytecode).
Prints constants, prototypes and a readable pseudo-disassembly.
"""
import struct, sys

class R:
    def __init__(s, d, p=0):
        s.d=d; s.p=p
    def u8(s):
        v=s.d[s.p]; s.p+=1; return v
    def u32(s):
        v=struct.unpack_from("<I", s.d, s.p)[0]; s.p+=4; return v
    def i32(s):
        v=struct.unpack_from("<i", s.d, s.p)[0]; s.p+=4; return v
    def u64(s):
        v=struct.unpack_from("<Q", s.d, s.p)[0]; s.p+=8; return v
    def f64(s):
        v=struct.unpack_from("<d", s.d, s.p)[0]; s.p+=8; return v
    def string(s):
        n=s.u32()
        if n==0: return None
        v=s.d[s.p:s.p+n-1]; s.p+=n; return v

class Proto:
    pass

def read_proto(r, parent_src):
    p=Proto()
    p.source=r.string() or parent_src
    p.line_defined=r.u32(); p.last_line_defined=r.u32()
    p.nups=r.u8(); p.numparams=r.u8(); p.is_vararg=r.u8(); p.maxstack=r.u8()
    n=r.u32(); p.code=[r.u32() for _ in range(n)]
    n=r.u32(); p.k=[]
    for _ in range(n):
        t=r.u8()
        if t==0: p.k.append(("nil",None))
        elif t==1: p.k.append(("bool",r.u8()))
        elif t==3: p.k.append(("num",r.f64()))
        elif t==4: p.k.append(("str",r.string()))
        else: raise ValueError("bad const tag %d"%t)
    n=r.u32(); p.p=[]
    for _ in range(n):
        p.p.append(read_proto(r, p.source))
    n=r.u32(); p.lineinfo=[r.i32() for _ in range(n)]
    n=r.u32(); p.locvars=[]
    for _ in range(n):
        name=r.string(); st=r.u32(); en=r.u32()
        p.locvars.append((name,st,en))
    n=r.u32(); p.upvals=[r.string() for _ in range(n)]
    return p

def load(path):
    d=open(path,"rb").read()
    if d[:4]!=b"\x1bLua": raise ValueError("not lua bytecode")
    if d[4]!=0x51: raise ValueError("not lua 5.1 (%#x)"%d[4])
    r=R(d,12)  # skip header + sizes
    return read_proto(r, None)

# --- opcode names / modes (Lua 5.1 lopcodes.c order)
OPS="""MOVE LOADK LOADBOOL LOADNIL GETUPVAL GETGLOBAL GETTABLE SETGLOBAL SETUPVAL
SETTABLE NEWTABLE SELF ADD SUB MUL DIV MOD POW UNM NOT LEN CONCAT JMP EQ LT LE
TEST TESTSET CALL TAILCALL RETURN FORLOOP FORPREP TFORLOOP SETLIST CLOSE CLOSURE
VARARG""".split()
OPMAP={i:n for i,n in enumerate(OPS)}

def kstr(p, bx, force=False):
    if bx>=len(p.k):
        return "K%d<oob>"%bx
    t,v=p.k[bx]
    if t=="str": return repr(v.decode("latin1"))
    if t=="num": return str(v)
    return "%s:%r"%(t,v)

def kget(p, i):
    """constant referenced by a C operand (register/constant union)"""
    if i>=256:
        return kstr(p, i-256)
    return "R%d"%i

def disasm(p, name="main", depth=0, out=sys.stdout):
    ind="  "*depth
    out.write(f"{ind}function <{name}> params={p.numparams} vararg={p.is_vararg} maxstack={p.maxstack} nups={p.nups}\n")
    if p.upvals: out.write(ind+"  upvals: "+", ".join(str(u) for u in p.upvals)+"\n")
    for i,ins in enumerate(p.code):
        op=ins&0x3f; A=(ins>>6)&0xff; C=(ins>>14)&0x1ff; B=(ins>>23)&0x1ff; Bx=(ins>>14)&0x3ffff
        nm=OPMAP.get(op,"OP%d"%op)
        args=""
        try:
            if nm in ("LOADK","GETGLOBAL","SETGLOBAL"): args=f"R{A} {kstr(p,Bx)}"
            elif nm=="CLOSURE": args=f"R{A} proto#{Bx}"
            elif nm=="GETUPVAL": args=f"R{A} upval[{B}]"
            elif nm=="SETUPVAL": args=f"upval[{B}] = R{A}"
            elif nm=="SELF": args=f"R{A} = R{B}[{kget(p,C)}]"
            elif nm in ("JMP","FORLOOP","FORPREP"): args=f"R{A} ->{i+1+Bx}"
            elif nm in ("EQ","LT","LE"): args=f"R{A} R{B} R{C}  (cond {A if False else B})"
            elif nm=="LOADBOOL": args=f"R{A} {B} skip={C}"
            elif nm=="LOADNIL": args=f"R{A}..R{A+B}"
            elif nm in ("GETTABLE","SETTABLE"): args=f"R{A} R{B} [{kget(p,C)}]"
            elif nm in ("ADD","SUB","MUL","DIV","MOD","POW"): args=f"R{A} = R{B} {nm.lower()} R{C}"
            elif nm=="RETURN": args=f"R{A}.. n={B}"
            elif nm=="CALL": args=f"R{A} nargs={B-1} nres={C-1}"
            elif nm=="SETLIST": args=f"R{A} n={B} C={C}"
            elif nm=="TEST": args=f"R{A} C={C}"
            elif nm=="TESTSET": args=f"R{A} B={B} C={C}"
            else: args=f"R{A} B={B} C={C}"
        except Exception as e:
            args=f"<decode err {e}> A={A} B={B} C={C} Bx={Bx}"
        out.write(f"{ind}  [{i:4d}] {nm:10s} {args}\n")
    for j,sp in enumerate(p.p):
        disasm(sp, f"{name}/p{j}", depth+1, out)

if __name__=="__main__":
    for f in sys.argv[1:]:
        p=load(f)
        sys.stdout.write(f"===== {f}\n")
        disasm(p)
