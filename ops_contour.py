# ops_contour.py
# Simple contour emission for Heidenhain TNC355
# FreeCAD-compatible version (Path.Command based)

from typing import List, Any
from emit_tnc import _append_changed, _CC, _C


def emit_contour_simple(
    out: List[str],
    commands: List[Any],
    state,
    feed_xy=None,
    feed_z=None,
    radius_comp=None,
):
    """
    Emit contour moves without LBL.

    Works directly on FreeCAD Path.Command objects.

    Rules:
    - Z is emitted only if it changes
    - XY is emitted if present
    - feed_xy is used for XY moves
    - feed_z is used for Z moves
    - rapid moves use FMAX
    """

    comp_pending = radius_comp or ""

    for cmd in commands:
        name = str(getattr(cmd, "Name", "")).upper()
        p = getattr(cmd, "Parameters", {}) or {}

        # ----------------------------
        # Linear moves (rapid / feed)
        # ----------------------------
        if name in ("G0", "G00", "G1", "G01"):
            x = p.get("X")
            y = p.get("Y")
            z = p.get("Z")
            rapid = name in ("G0", "G00")

            # Z move first
            if z is not None:
                if state.z is None or abs(state.z - z) > 1e-9:
                    _append_changed(
                        out,
                        z=z,
                        f="FMAX" if rapid else feed_z,
                        state=state,
                    )
                    state.z = z

            # XY move
            if x is not None or y is not None:
                start_len = len(out)
                comp = comp_pending if comp_pending and not rapid else ""
                _append_changed(
                    out,
                    x=x,
                    y=y,
                    f="FMAX" if rapid else feed_xy,
                    korrektur=comp,
                    state=state,
                )
                if len(out) > start_len and comp:
                    comp_pending = ""
                if x is not None:
                    state.x = x
                if y is not None:
                    state.y = y

        # ----------------------------
        # Arc moves (G2 / G3)
        # ----------------------------
        elif name in ("G2", "G02", "G3", "G03"):
            # optional Z before arc
            z = p.get("Z")
            if z is not None:
                if state.z is None or abs(state.z - z) > 1e-9:
                    _append_changed(out, z=z, f=feed_z, state=state)
                    state.z = z

            # arc center + end point
            cx = p.get("I")
            cy = p.get("J")
            x = p.get("X")
            y = p.get("Y")
            cw = name in ("G2", "G02")

            if cx is not None and cy is not None:
                out.append(_CC(cx, cy))
            comp = comp_pending if comp_pending else ""
            out.append(_C(x, y, cw=cw, korrektur=comp))
            if comp:
                comp_pending = ""

            state.x = x
            state.y = y

        # ----------------------------
        # Ignore all other commands
        # ----------------------------
        else:
            continue
