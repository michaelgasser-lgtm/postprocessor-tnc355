# tool_db.py - Tool database (single source of truth) + CSV (FreeCAD Job.Tools.Group)
from __future__ import annotations

from dataclasses import dataclass
import csv
from typing import Any, Optional


@dataclass
class ToolInfo:
    tnum: int
    label: str = ""
    diam_mm: Optional[float] = None
    rpm: Optional[int] = None
    feed_xy_mmmin: Optional[int] = None
    feed_z_mmmin: Optional[int] = None


class ToolDB:
    def __init__(self):
        self.tools: dict[int, ToolInfo] = {}

    def get(self, tnum: Optional[int]) -> Optional[ToolInfo]:
        if tnum is None:
            return None
        return self.tools.get(int(tnum))


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        # FreeCAD Quantity -> float works in most cases
        return float(v)
    except Exception:
        try:
            return float(str(v).split()[0])
        except Exception:
            return None


def _to_int(v: Any) -> Optional[int]:
    f = _to_float(v)
    if f is None:
        return None
    try:
        return int(round(f))
    except Exception:
        return None


def _qty_mmps_to_mmmin(v: Any) -> Optional[int]:
    """Convert FreeCAD Quantity value (typically mm/s) to mm/min."""
    f = _to_float(v)
    if f is None:
        return None
    return int(round(f * 60.0))


def _get_prop(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    if hasattr(obj, name):
        try:
            return getattr(obj, name)
        except Exception:
            return None
    return None


def _find_tool_controllers_from_job(job) -> list:
    """
    Your FreeCAD setup:
      job.Tools is a DocumentObjectGroup
      tool controllers are in job.Tools.Group
    """
    tgroup = getattr(job, "Tools", None)
    if not tgroup:
        return []
    kids = list(getattr(tgroup, "Group", []) or [])
    return kids


def build_tool_db(job, operations=None) -> ToolDB:
    db = ToolDB()

    controllers = _find_tool_controllers_from_job(job)

    for tc in controllers:
        # Tool number
        tnum = _get_prop(tc, "ToolNumber")
        try:
            tnum_i = int(tnum)
        except Exception:
            # if ToolNumber is missing, we cannot reference it reliably
            continue

        label = str(getattr(tc, "Label", "") or getattr(tc, "Name", "") or f"Tool{tnum_i}")

        # Link to toolbit (for diameter etc.)
        tool = _get_prop(tc, "Tool") or _get_prop(tc, "Toolbit") or _get_prop(tc, "ToolBit")

        # Diameter (best effort; depends on your toolbit model)
        diam = None
        if tool is not None:
            diam = _get_prop(tool, "Diameter") or _get_prop(tool, "ToolDiameter") or _get_prop(tool, "Diam")
        diam_mm = _to_float(diam)

        # RPM (best effort; depends on your controller model)
        rpm = _get_prop(tc, "SpindleSpeed") or _get_prop(tc, "RPM") or _get_prop(tc, "Spindle")
        rpm_i = _to_int(rpm)

        # Feeds: you have them on the controller as Quantity in mm/s
        fxy_q = _get_prop(tc, "HorizFeed")
        fz_q  = _get_prop(tc, "VertFeed")

        info = ToolInfo(
            tnum=tnum_i,
            label=label,
            diam_mm=diam_mm,
            rpm=rpm_i,
            feed_xy_mmmin=_qty_mmps_to_mmmin(fxy_q),
            feed_z_mmmin=_qty_mmps_to_mmmin(fz_q),
        )

        db.tools[tnum_i] = info

    return db


def write_tool_csv(db: ToolDB, filepath: str) -> None:
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ToolNumber", "Label", "Diameter_mm", "Spindle_rpm", "FeedXY_mmmin", "FeedZ_mmmin"])
        for tnum in sorted(db.tools):
            t = db.tools[tnum]
            w.writerow([t.tnum, t.label, t.diam_mm, t.rpm, t.feed_xy_mmmin, t.feed_z_mmmin])


def check_toolnumbers_unique(db: ToolDB) -> None:
    # Here db.tools already deduplicates by key, but we keep the API for your workflow.
    if not db.tools:
        raise RuntimeError(
            "FEHLER: Keine Werkzeuge gefunden.\n"
            "Bitte prüfen: Job.Tools.Group enthält ToolController mit ToolNumber."
        )
