# -*- coding: utf-8 -*-
"""Run pure-Python work on a thread with a large stack.

Revit died with a stack overflow (0xc00000fd) while the BOQ tool wrote a
workbook for a rebar (BBS) model on 2026-09-22. The writers themselves are
shallow - replayed with the real rows they ran on a 128 KB stack - but
under pyRevit's IronPython engine they run at the bottom of a very deep
call chain on Revit's main thread (external event, pyRevit, the dialog,
the export handler), and whichever step went a little deeper - the Rebar
sheet one time, the P13 summaries the next - crossed the edge.

The workbook writers touch no Revit API, so they can run on their own
thread with a stack sized for the job. Revit API work must stay on the
main thread; never pass it here.

Pure Python. Without .NET (plain CPython, the regression harness) the
function simply runs in place.
"""
import sys

DEFAULT_STACK_BYTES = 64 * 1024 * 1024


def run_with_large_stack(function, *args, **kwargs):
    """Call function(*args, **kwargs) on a large-stack thread; return its
    result, or re-raise its exception here with the original traceback
    text attached."""
    stack_bytes = kwargs.pop("_stack_bytes", DEFAULT_STACK_BYTES)
    try:
        from System.Threading import Thread, ThreadStart
    except Exception:
        return function(*args, **kwargs)

    box = {}

    def work():
        try:
            box["result"] = function(*args, **kwargs)
        except BaseException:
            box["error"] = sys.exc_info()

    worker = Thread(ThreadStart(work), stack_bytes)
    # Same number/date formatting as the calling thread, so the workbook
    # is written exactly as it was on the main thread.
    try:
        worker.CurrentCulture = Thread.CurrentThread.CurrentCulture
        worker.CurrentUICulture = Thread.CurrentThread.CurrentUICulture
    except Exception:
        pass
    worker.Start()
    worker.Join()

    if "error" in box:
        error = box["error"][1]
        try:
            import traceback
            error.worker_traceback = "".join(
                traceback.format_exception(*box["error"]))
        except Exception:
            pass
        raise error
    return box.get("result")
