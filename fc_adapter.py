# fc_adapter.py - FreeCAD/CAM adapter utilities
from __future__ import annotations

def unwrap_base(obj):
    """Follow .Base chain (Dressups) until the real operation object."""
    base = obj
    for _ in range(16):
        b = getattr(base, "Base", None)
        if not b:
            break
        base = b
    return base

def get_heights(obj, default_safe=5.0, default_clear=50.0):
    """Return (safe_z, clear_z) from operation properties (absolute heights)."""
    base = unwrap_base(obj)
    safe = getattr(base, "SafeHeight", None)
    clear = getattr(base, "ClearanceHeight", None)
    try:
        safe_z = float(safe)
    except Exception:
        safe_z = float(default_safe)
    try:
        clear_z = float(clear)
    except Exception:
        clear_z = float(default_clear)
    return safe_z, clear_z

def scan_command_names(pth):
    names=set()
    for c in getattr(pth, "Commands", []) or []:
        n = str(getattr(c, "Name", "")).upper()
        if n:
            names.add(n)
    return names
