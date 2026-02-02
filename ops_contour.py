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
    op=None,
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

    def _iter_op_chain(root):
        cur = root
        seen = set()
        for _ in range(16):
            if cur is None or id(cur) in seen:
                break
            seen.add(id(cur))
            yield cur
            cur = getattr(cur, "Base", None)

    def _get_op_attr(root, name):
        for obj in _iter_op_chain(root):
            if hasattr(obj, name):
                try:
                    value = getattr(obj, name)
                except Exception:
                    continue
                if value is not None:
                    return value
        return None

    def _normalize_token(value):
        if value is None:
            return None
        try:
            text = str(value)
        except Exception:
            return None
        return text.strip().lower()

    def _normalize_bool(value):
        if isinstance(value, bool):
            return value
        token = _normalize_token(value)
        if token in ("1", "true", "yes", "y", "on"):
            return True
        if token in ("0", "false", "no", "n", "off"):
            return False
        return False

    use_comp = _get_op_attr(op, "UseComp")
    side = _get_op_attr(op, "Side")
    direction = _get_op_attr(op, "Direction")
    out.append(
        f"(DEBUG UseComp={use_comp!r} type={type(use_comp).__name__} | "
        f"Side={side!r} type={type(side).__name__} | "
        f"Direction={direction!r} type={type(direction).__name__})"
    )

    use_comp_bool = _normalize_bool(use_comp)
    side_token = _normalize_token(side)
    direction_token = _normalize_token(direction)

    radius_mode = "R0"
    if not use_comp_bool:
        if side_token in ("left", "l", "g41", "rl"):
            radius_mode = "RL"
        elif side_token in ("right", "r", "g42", "rr"):
            radius_mode = "RR"
        elif side_token in ("inside", "inner", "in"):
            if direction_token in ("cw", "clockwise"):
                radius_mode = "RR"
            elif direction_token in ("ccw", "counterclockwise", "anti-clockwise", "anticlockwise"):
                radius_mode = "RL"
        elif side_token in ("outside", "outer", "out"):
            if direction_token in ("cw", "clockwise"):
                radius_mode = "RL"
            elif direction_token in ("ccw", "counterclockwise", "anti-clockwise", "anticlockwise"):
                radius_mode = "RR"

    out.append(f"(RADIUS_MODE={radius_mode})")

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
                comp = ""
                if not rapid:
                    if comp_pending == "R0":
                        comp = comp_pending
                    elif comp_pending in ("RL", "RR"):
                        if seen_first_feed:
                            comp = comp_pending
                _append_changed(
                    out,
                    x=x,
                    y=y,
                    f="FMAX" if rapid else feed_xy,
                    korrektur=comp,
                    state=state,
                )
                if len(out) > start_len:
                    if not rapid:
                        if not seen_first_feed:
                            seen_first_feed = True
                        elif comp:
                            comp_pending = ""
                        if comp == "R0":
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
            comp = ""
            if comp_pending == "R0":
                comp = comp_pending
            elif comp_pending in ("RL", "RR"):
                if seen_first_feed:
                    comp = comp_pending
            out.append(_C(x, y, cw=cw, korrektur=comp))
            if not seen_first_feed:
                seen_first_feed = True
            elif comp:
                comp_pending = ""
            if comp == "R0":
                comp_pending = ""

            state.x = x
            state.y = y

        # ----------------------------
        # Ignore all other commands
        # ----------------------------
        else:
            continue
