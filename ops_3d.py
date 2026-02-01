from __future__ import annotations
from emit_tnc import _append_changed, _CC, _C

def emit_3d(out, state, tooldb, heights, pth):
    for cmd in getattr(pth, "Commands", []) or []:
        n = str(getattr(cmd, "Name", "")).upper()
        p = getattr(cmd, "Parameters", {}) or {}
        if n in ("G0","G00"):
            _append_changed(out, x=p.get("X"), y=p.get("Y"), z=p.get("Z"), f="FMAX", state=state)
            if p.get("X") is not None:
                state.x = p.get("X")
            if p.get("Y") is not None:
                state.y = p.get("Y")
            if p.get("Z") is not None:
                state.z = p.get("Z")
        elif n in ("G1","G01"):
            _append_changed(out, x=p.get("X"), y=p.get("Y"), z=p.get("Z"), f=p.get("F"), state=state)
            if p.get("X") is not None:
                state.x = p.get("X")
            if p.get("Y") is not None:
                state.y = p.get("Y")
            if p.get("Z") is not None:
                state.z = p.get("Z")
        elif n == "CC":
            out.append(_CC(p.get("X"), p.get("Y")))
        elif n == "C":
            out.append(_C(p.get("X"), p.get("Y"), cw=bool(p.get("DR", True))))
