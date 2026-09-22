# -*- coding: utf-8 -*-
"""Crash trail - one flushed line per step, so a hard crash leaves a clue.

On 2026-09-22 Revit died three times with a stack overflow (0xc00000fd)
while the BOQ tool ran on a rebar (BBS) model. A stack overflow kills the
process outright: no Python traceback, no pyRevit log. This module writes
a short line before each step and flushes it to the operating system at
once, so the last line in the file names the step - and the element -
that was running when Revit went down.

Pure Python (os / time only); every call is guarded so the trail can
never be the reason an export fails.
"""
import os
import time

MAX_TRAIL_BYTES = 2 * 1024 * 1024


def _logs_folder():
    root = os.environ.get("LOCALAPPDATA", "") or os.path.expanduser("~")
    return os.path.join(root, "RCC_BOQ", "logs")


def trail_path():
    try:
        return os.path.join(_logs_folder(), "boq_crash_trail.log")
    except Exception:
        return ""


def mark(step):
    """Append one line and flush it; never raises.

    RCC_BOQ_NO_TRAIL=1 turns it off, so the regression harness does not
    write into the owner's trail.
    """
    try:
        if os.environ.get("RCC_BOQ_NO_TRAIL"):
            return
        path = trail_path()
        if not path:
            return
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        if os.path.isfile(path) and os.path.getsize(path) > MAX_TRAIL_BYTES:
            old = path + ".old"
            if os.path.isfile(old):
                os.remove(old)
            os.rename(path, old)
        try:
            pid = os.getpid()
        except Exception:
            pid = "?"
        handle = open(path, "a")
        try:
            handle.write("{0} pid={1} {2}\n".format(
                time.strftime("%Y-%m-%d %H:%M:%S"), pid, step))
            handle.flush()
        finally:
            handle.close()
    except Exception:
        pass

