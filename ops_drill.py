# ops_drill.py - Drilling emitter (FreeCAD drilling ops -> Heidenhain TNC355)
from __future__ import annotations

"""Drilling emitter.

FreeCAD drilling ops typically produce a small G-code-like command stream (G81/G82/G83)
inside Path.Commands. We translate that into Heidenhain cycles and group identical
cycle definitions for multiple XY points.

Important: This post is loaded by FreeCAD as a standalone script (not a package).
Therefore we only use absolute imports (same-folder modules) and rely on the entry
script (tnc355_post.py) to place this folder on sys.path.
"""

from typing import Any, Dict, List, Optional, Tuple

from emit_tnc import (
    _L,
    _append_unique,
    _fmt_number,
    _fmt_negative,
    _fmt_time_seconds_with_comma,
    _fmt_feed_num_scaled,
)


def _warn(out: List[str], msg: str) -> None:
    # Heidenhain comments are fine for diagnostics.
    out.append(f"; WARN: {msg}")


def _dg_key(kind: str, depth: Any, rplane: Any, feed: Any, dwell: Any, peck: Any) -> Tuple:
    """Create a stable grouping key for drilling cycles."""
    def _q(v: Any, nd: int = 6):
        try:
            return round(float(v), nd)
        except Exception:
            return v

    return (
        str(kind).upper(),
        _q(depth),
        _q(rplane),
        _q(feed),
        _q(dwell),
        _q(peck),
    )


def _emit_cycle_def(out: List[str], dg: Dict[str, Any]) -> None:
    """Emit Heidenhain CYCL DEF lines for current drill group."""
    kind = str(dg.get("kind", "G81")).upper()
    depth = dg.get("depth", -5.0)
    rplane = dg.get("r", 2.0)
    feed = dg.get("feed", 80)
    dwell = dg.get("dwell", 0) or 0
    peck = dg.get("peck", None)

    # Convert to strings with correct decimal and sign conventions
    abst = _fmt_negative(rplane)  # ABST uses negative sign in your preferred output
    tiefe = _fmt_number(depth, "+.3f")

    # Feed: FreeCAD usually provides mm/s, we scale to mm/min like emit_tnc does.
    fnum = _fmt_feed_num_scaled(feed)
    if fnum is None:
        fnum = 60

    # Dwell format with comma
    vzeit = _fmt_time_seconds_with_comma(dwell)

    out.append("CYCL DEF 1.0 TIEFBOHREN")
    out.append(f"CYCL DEF 1.1 ABST {abst}")
    out.append(f"CYCL DEF 1.2 TIEFE {tiefe}")
    if peck is not None:
        out.append(f"CYCL DEF 1.3 ZUSTLG {_fmt_negative(peck)}")
    else:
        out.append(f"CYCL DEF 1.3 ZUSTLG {tiefe}")
    if kind == "G82":
        out.append(f"CYCL DEF 1.4 VZEIT {vzeit}")
    else:
        out.append("CYCL DEF 1.4 VZEIT 0,000")
    out.append(f"CYCL DEF 1.5 F {fnum}")


def _flush_drill_group(out: List[str], dg: Dict[str, Any]) -> None:
    """Flush pending drill group: emit cycle def + XY points as CYCL CALL."""
    if not dg.get("active"):
        return

    pts = dg.get("pts") or []
    if not pts:
        dg["active"] = False
        return

    _emit_cycle_def(out, dg)
    for (x, y) in pts:
        # Rapid to XY, then cycle call
        _append_unique(out, _L(x=x, y=y, f="FMAX"))
        out.append("CYCL CALL")

    dg["active"] = False
    dg["pts"] = []


def _normalize_state(state: Any) -> Dict[str, Any]:
    if hasattr(state, "__dict__") and not isinstance(state, dict):
        state = state.__dict__
    if not isinstance(state, dict):
        state = {}
    state.setdefault("X", None)
    state.setdefault("Y", None)
    state.setdefault("Z", None)
    return state


def _emit_literal_with_drill_grouping(out: List[str], pth, state: Any, peck=None) -> None:
    state = _normalize_state(state)
    if not pth:
        return

    dg: Dict[str, Any] = {"active": False}

    for cmd in getattr(pth, "Commands", []) or []:
        name = str(getattr(cmd, "Name", "")).upper()
        par = dict(getattr(cmd, "Parameters", {}) or {})

        # ignore wrappers / modal noise
        if name in ("(DRILLING)", "(BEGIN DRILLING)", "G90", "G98"):
            continue

        if name == "G80":
            if peck is not None:
                dg["peck"] = peck
            _flush_drill_group(out, dg)
            continue

        X = par.get("X", state.get("X"))
        Y = par.get("Y", state.get("Y"))
        Z = par.get("Z", state.get("Z"))
        F = par.get("F", None)

        if name in ("G0", "G00"):
            _append_unique(out, _L(x=X, y=Y, z=Z, f="FMAX"))

        elif name in ("G1", "G01"):
            out.append(_L(x=X, y=Y, z=Z, f=F))

        elif name in ("G81", "G82", "G83"):
            depth = par.get("Z", -5.0)
            rplane = par.get("R", 2.0)
            feed = par.get("F", 80)
            dwell = par.get("P", 0.0) if name == "G82" else 0.0

            key = _dg_key(name, depth, rplane, feed, dwell, peck)
            if (not dg.get("active")) or dg.get("key") != key:
                if peck is not None:
                    dg["peck"] = peck
                _flush_drill_group(out, dg)
                dg.update(
                    {
                        "active": True,
                        "key": key,
                        "kind": name,
                        "depth": depth,
                        "r": rplane,
                        "feed": feed,
                        "dwell": dwell or None,
                        "peck": peck,
                        "pts": [],
                    }
                )

            dg["pts"].append((par.get("X", state.get("X")), par.get("Y", state.get("Y"))))

        else:
            # Keep going; don't hard-fail on unknown command
            _warn(out, f"UNSUPPORTED {name} {par}")

        # update modals
        if X is not None:
            state["X"] = X
        if Y is not None:
            state["Y"] = Y
        if Z is not None:
            state["Z"] = Z

    if peck is not None:
        dg["peck"] = peck
    _flush_drill_group(out, dg)


def emit_drilling(out: List[str], state: Any, tooldb, heights, pth) -> None:
    """Emit a drilling operation.

    Note: Approach/retract logic (safe/clear) is currently handled at a higher level.
    Here we only translate the drilling command stream into cycles.
    """
    _emit_literal_with_drill_grouping(out, pth, state, peck=None)
