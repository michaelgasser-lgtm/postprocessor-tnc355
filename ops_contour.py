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

    def _get_prop(obj, name):
        if obj is None:
            return None
        if hasattr(obj, name):
            try:
                return getattr(obj, name)
            except Exception:
                return None
        return None

    def _to_float(value):
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            try:
                return float(str(value).split()[0])
            except Exception:
                return None

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

    first_xy_index = None
    for idx, cmd in enumerate(commands):
        name = str(getattr(cmd, "Name", "")).upper()
        if name not in ("G0", "G00", "G1", "G01"):
            continue
        p = getattr(cmd, "Parameters", {}) or {}
        if p.get("X") is not None or p.get("Y") is not None:
            first_xy_index = idx
            break

    if first_xy_index is None:
        entry_index = None
        lead_in = False
    else:
        entry_index = first_xy_index
        lead_in = any(
            str(getattr(cmd, "Name", "")).upper() in ("G0", "G00", "G1", "G01")
            and (
                (getattr(cmd, "Parameters", {}) or {}).get("X") is not None
                or (getattr(cmd, "Parameters", {}) or {}).get("Y") is not None
            )
            for idx, cmd in enumerate(commands[:entry_index])
        )

    tool_diam = None
    tool_controller = _get_op_attr(op, "ToolController")
    if tool_controller is not None:
        tool = (
            _get_prop(tool_controller, "Tool")
            or _get_prop(tool_controller, "Toolbit")
            or _get_prop(tool_controller, "ToolBit")
        )
        tool_diam = (
            _get_prop(tool, "Diameter")
            or _get_prop(tool, "ToolDiameter")
            or _get_prop(tool, "Diam")
        )
    if tool_diam is None:
        tool_diam = (
            _get_op_attr(op, "Diameter")
            or _get_op_attr(op, "ToolDiameter")
            or _get_op_attr(op, "Diam")
        )

    tool_diam_mm = _to_float(tool_diam)
    tool_radius = tool_diam_mm / 2.0 if tool_diam_mm else 0.0
    rnd_radius = round(max(1.05 * tool_radius, tool_radius + 0.5), 1)

    out.append(f"(DEBUG LeadIn={lead_in})")
    out.append(f"(DEBUG EntryIndex={entry_index})")
    out.append(f"(DEBUG RND_RADIUS={rnd_radius})")
    out.append(f"(DEBUG RADIUS_MODE={radius_mode})")

    if radius_mode in ("RL", "RR") and (not lead_in or entry_index is None):
        out.append("(ERROR: RL/RR requires Lead-In)")
        out.append("(Contour aborted)")
        return

    rnd_emitted = False

    for idx, cmd in enumerate(commands):
        name = str(getattr(cmd, "Name", "")).upper()
        p = getattr(cmd, "Parameters", {}) or {}
        phase_before_entry = entry_index is not None and idx < entry_index
        phase_entry = entry_index is not None and idx == entry_index

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
                comp = ""
                if phase_before_entry:
                    comp = "R0"
                elif phase_entry and radius_mode in ("RL", "RR"):
                    if not rnd_emitted:
                        out.append(f"RND R{rnd_radius:.1f}")
                        rnd_emitted = True
                    comp = radius_mode
                _append_changed(
                    out,
                    x=x,
                    y=y,
                    f="FMAX" if rapid else feed_xy,
                    korrektur=comp,
                    state=state,
                )
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
            out.append(_C(x, y, cw=cw))

            state.x = x
            state.y = y

        # ----------------------------
        # Ignore all other commands
        # ----------------------------
        else:
            continue
