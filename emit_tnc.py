from __future__ import annotations
import re

RAPID_FEED = 9999

_FEED_MODAL = None

_TOOL_INITIALIZED = False

def reset_modals():
    global _FEED_MODAL
    _FEED_MODAL = None

def _fmt_coord(prefix, val, nd=3):
    try:
        f = float(val)
    except Exception:
        return None
    sign = "+" if f >= 0 else ""
    return f"{prefix}{sign}{f:.{nd}f}"

def safe_z(out, z):
    """
    Fahre sicher auf Z-Höhe mit FMAX.
    Nur erlaubt, wenn bereits ein Werkzeug initialisiert ist.
    """
    if not _TOOL_INITIALIZED:
        return
    out.append(f"L  Z+{z:.3f}  FMAX")

def stop_spindle(out):
    """Spindel stoppen (M5)."""
    out.append("L  M5")


def start_spindle(out):
    """Spindel starten (M3)."""
    out.append("L  M3")


def coolant_off(out):
    """Kühlmittel aus (M9)."""
    out.append("L  M9")


def coolant_on(out):
    """Kühlmittel ein (M8)."""
    out.append("L  M8")


def tool_change(out):
    """Werkzeugwechsel (M6)."""
    out.append("L  M6")


def _fmt_feed_num(v):
    try:
        return int(round(float(v)))
    except Exception:
        return None

def tool_call(out, tnum, rpm=None):
    global _TOOL_INITIALIZED    
    """
    Heidenhain TOOL CALL.
    Beispiel:
      TOOL CALL 3 Z S12000
    """
    if rpm:
        out.append(f"TOOL CALL {int(tnum)} Z S{int(rpm)}")
    else:
        out.append(f"TOOL CALL {int(tnum)} Z")
    _TOOL_INITIALIZED = True

_AXIS_RE = re.compile(r'(?:^|\s)([XYZ])([+-]?\d+(?:\.\d+)?)')

def _extract_axes_from_line(line: str):
    if not line or not isinstance(line, str):
        return (None, None, None)
    if not line.lstrip().startswith("L"):
        return (None, None, None)
    x=y=z=None
    for ax, val in _AXIS_RE.findall(line):
        try:
            f=float(val)
        except Exception:
            continue
        if ax=="X": x=f
        elif ax=="Y": y=f
        elif ax=="Z": z=f
    return (x,y,z)

def _state_coords(state):
    if state is None:
        return (None, None, None)
    if isinstance(state, dict):
        return (state.get("x"), state.get("y"), state.get("z"))
    return (getattr(state, "x", None), getattr(state, "y", None), getattr(state, "z", None))


def _append_changed(out, x=None, y=None, z=None, f=None, korrektur="", state=None):
    last_x, last_y, last_z = _state_coords(state)
    if last_x is None and last_y is None and last_z is None and out:
        last_x, last_y, last_z = _extract_axes_from_line(out[-1])

    axis_changed = False
    if x is not None and (last_x is None or abs(float(x) - last_x) > 1e-6):
        axis_changed = True
    if y is not None and (last_y is None or abs(float(y) - last_y) > 1e-6):
        axis_changed = True
    if z is not None and (last_z is None or abs(float(z) - last_z) > 1e-6):
        axis_changed = True

    if not axis_changed:
        return

    out.append(_L(x=x, y=y, z=z, f=f, korrektur=korrektur))

def _append_unique(out, line: str):
    """Append line only if it differs from the last emitted line."""
    if line is None:
        return
    if not out or out[-1] != line:
        out.append(line)


def _L(x=None, y=None, z=None, f=None, korrektur=""):
    global _FEED_MODAL
    parts = ["L"]
    if x is not None:
        parts.append(_fmt_coord("X", x))
    if y is not None:
        parts.append(_fmt_coord("Y", y))
    if z is not None:
        parts.append(_fmt_coord("Z", z))
    if korrektur:
        parts.append(korrektur)

    if f is not None:
        if isinstance(f, str) and f.upper() == "FMAX":
            parts.append(f"F{RAPID_FEED}")
        else:
            fnum = _fmt_feed_num(f)
            if fnum is not None and fnum != _FEED_MODAL:
                parts.append(f"F{fnum}")
                _FEED_MODAL = fnum

    return "  ".join(parts)

def _CC(cx, cy):
    return f"CC  {_fmt_coord('X', cx)}  {_fmt_coord('Y', cy)}"

def _C(x, y, cw=True, korrektur=""):
    line = f"C  {_fmt_coord('X', x)}  {_fmt_coord('Y', y)}  {'DR-' if cw else 'DR+'}"
    if korrektur:
        line += f" {korrektur}"
    return line

def _fmt_number(v, fmt="+.3f"):
    try:
        return format(float(v), fmt)
    except Exception:
        return str(v)


def _fmt_negative(v):
    try:
        f = float(v)
    except Exception:
        try:
            f = float(str(v).replace("+", "").replace(",", "."))
        except Exception:
            return "-0.000"
    if f >= 0:
        f = -abs(f)
    return f"{f:+.3f}"


def _fmt_time_seconds_with_comma(v, decimals=3):
    try:
        f = float(v)
    except Exception:
        return "0,000"
    s = f"{f:.{decimals}f}"
    return s.replace(".", ",")


def _fmt_feed_num_scaled(v, scale=60.0):
    try:
        return int(round(float(v) * scale))
    except Exception:
        return None
