from __future__ import annotations
import os, sys

_here = os.path.dirname(globals().get("__file__", "")) or os.getcwd()
if _here not in sys.path:
    sys.path.insert(0, _here)

import FreeCAD as App  # type: ignore

from state import State
from fc_adapter import unwrap_base, get_heights
from tool_db import build_tool_db, write_tool_csv, check_toolnumbers_unique
from router import classify
import emit_tnc
from ops_drill import emit_drilling
from ops_contour import emit_contour_simple
from ops_3d import emit_3d

TOOLCHANGE_Z = 150.0


def _find_job(doc):
    try:
        return doc.getObject("Job")
    except Exception:
        return None


def _tools_csv_path(job):
    out_file = getattr(job, "PostProcessorOutputFile", None)
    if not out_file or out_file in ("-", ""):
        return None
    base, _ = os.path.splitext(out_file)
    return base + "_tools.csv"


def _program_name(job):
    out_file = getattr(job, "PostProcessorOutputFile", None)
    if out_file and out_file not in ("-", ""):
        return os.path.splitext(os.path.basename(out_file))[0]
    return "PROGRAM"


def _get_tool_number(op):
    # 1) direktes Tool an der Operation
    tc = getattr(op, "ToolController", None)
    if tc is not None:
        try:
            return int(tc.ToolNumber)
        except Exception:
            pass

    # 2) Dressup → Basis-Operation
    base = getattr(op, "Base", None)
    if base is not None:
        tc = getattr(base, "ToolController", None)
        if tc is not None:
            try:
                return int(tc.ToolNumber)
            except Exception:
                pass

    return None


def export(objectslist, filename, args=""):
    import FreeCAD as App  # wichtig: lokaler Import

    doc = App.ActiveDocument
    job = _find_job(doc)

    emit_tnc.reset_modals()
    state = State()

    db = build_tool_db(job)
    csv = _tools_csv_path(job)
    if csv:
        write_tool_csv(db, csv)
    check_toolnumbers_unique(db)

    out = []
    name = _program_name(job)
    out.append(f"BEGIN PGM {name} MM")

    for obj in job.Operations.Group:
        if not getattr(obj, "Active", True):
            continue

        base = unwrap_base(obj)
        pth = getattr(obj, "Path", None) or getattr(base, "Path", None)
        if not pth:
            continue

        # ===== TOOL CALL =====
        new_tool = _get_tool_number(obj)
        if new_tool is not None and new_tool != state.tool_active:
            tool = db.get(new_tool)
            rpm = tool.rpm if tool else 0

            emit_tnc.safe_z(out, TOOLCHANGE_Z)
            emit_tnc.stop_spindle(out)
            emit_tnc.coolant_off(out)
            emit_tnc.tool_change(out)

            if rpm:
                emit_tnc.tool_call(out, new_tool, rpm)
            else:
                emit_tnc.tool_call(out, new_tool)

            emit_tnc.start_spindle(out)
            emit_tnc.coolant_on(out)

            state.tool_active = new_tool
        # =====================

        tool = db.get(state.tool_active)
        fx = tool.feed_xy_mmmin if tool else None
        fz = tool.feed_z_mmmin if tool else None

        kind = classify(pth)
        if kind == "drill":
            emit_drilling(out, state, db, get_heights(obj), pth)
        elif kind == "3d":
            emit_3d(out, state, db, get_heights(obj), pth)
        else:
            emit_contour_simple(out, pth.Commands, state, fx, fz)

    out.append(f"END PGM {name} MM")
    return "\n".join(f"{i} {l}" for i, l in enumerate([""] + out)) + "\n"
