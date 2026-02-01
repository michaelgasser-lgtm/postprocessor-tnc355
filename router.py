# router.py - operation classification
from __future__ import annotations
from fc_adapter import scan_command_names

DRILL_CMDS = {"G81","G82","G83","G73"}

def classify(pth):
    names = scan_command_names(pth)
    if names & DRILL_CMDS:
        return "drill"
    # crude heuristic: if there are many commands and lots of Z variation -> 3d
    cmds = getattr(pth, "Commands", []) or []
    if len(cmds) > 500:
        return "3d"
    return "contour"
