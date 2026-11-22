"""
libreport.py — progress reporting, cancellation and time budget for GLOMOS runs.

The original web integration scraped GLOMOS' stdout with regular expressions
(``GENERATION n``, ``#1 name -123.4 kcal/mol`` ...). Any change in a print()
silently broke the progress bar. The GA now talks to a ``Reporter`` instead:

* ``reporter.log(msg)``            human-readable line (also printed)
* ``reporter.event(type, **data)`` structured event (JSON-serialisable)
* ``reporter.check()``             raises ``Stopped`` on cancel / timeout

In the worker subprocess events are written to stdout as
``@@ELAYA@@{json}`` lines which the parent parses (see elaya_jobs.py).
"""
import json
import os
import sys
import time

EVENT_PREFIX = "@@ELAYA@@"


class Stopped(Exception):
    """Raised inside the GA when the run was cancelled or ran out of time."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason          # 'cancelled' | 'timeout'


class Reporter:
    def __init__(self, emit=None, deadline=None, cancel_file=None, echo=True):
        """
        emit        callable(dict) receiving structured events; default writes
                    ``@@ELAYA@@{json}`` lines to stdout
        deadline    absolute time.time() after which Stopped('timeout') is raised
        cancel_file path whose existence means 'cancel' (cross-platform signal)
        """
        self._emit = emit if emit is not None else self._stdout_emit
        self.deadline = deadline
        self.cancel_file = cancel_file
        self.echo = echo
        self.t0 = time.time()

    @staticmethod
    def _stdout_emit(evt):
        sys.stdout.write(EVENT_PREFIX + json.dumps(evt) + "\n")
        sys.stdout.flush()

    def event(self, type, **data):
        evt = {"type": type, "t": round(time.time() - self.t0, 2)}
        evt.update(data)
        self._emit(evt)

    def log(self, msg):
        if self.echo and self._emit is not self._stdout_emit:
            print(msg)
        self.event("log", line=str(msg))

    def stop_reason(self):
        if self.cancel_file and os.path.exists(self.cancel_file):
            return "cancelled"
        if self.deadline is not None and time.time() > self.deadline:
            return "timeout"
        return None

    def check(self):
        reason = self.stop_reason()
        if reason:
            raise Stopped(reason)


def console_reporter(deadline=None, cancel_file=None):
    """Reporter that only prints human-readable log lines (command-line use)."""
    def _emit(evt):
        if evt.get("type") == "log":
            print(evt["line"], flush=True)
    return Reporter(emit=_emit, deadline=deadline, cancel_file=cancel_file, echo=False)
