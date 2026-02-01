# router.py - operation classification
from __future__ import annotations
import Path.Op.Profile
from fc_adapter import scan_command_names

DRILL_CMDS = {"G81","G82","G83","G73"}

def classify(pth, base=None):
    if base is not None and isinstance(getattr(base, "Proxy", None), Path.Op.Profile.ObjectProfile):
        return "contour"
    names = scan_command_names(pth)
    if names & DRILL_CMDS:
        return "drill"
    # crude heuristic: if there are many commands and lots of Z variation -> 3d
    cmds = getattr(pth, "Commands", []) or []
    if len(cmds) > 500:
        return "3d"
    return "contour"
