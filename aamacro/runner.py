"""Loads a macro file and runs its run(m) on a background thread."""
import importlib.util
import threading
import traceback
from pathlib import Path

from . import inputs
from .api import Macro, MacroStopped


def list_macros(folder):
    """Macro files in the folder; names starting with "_" are hidden."""
    return sorted(p for p in Path(folder).glob("*.py") if not p.name.startswith("_"))


def _load(path):
    # A fresh module every run, so edits to the file apply without restarting.
    spec = importlib.util.spec_from_file_location(f"macro_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if not callable(run):
        raise RuntimeError(f"{path.name} needs a function:  def run(m):")
    return run


class MacroRunner:
    def __init__(self, log):
        self._log = log
        self._thread = None
        self._stop = threading.Event()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, path):
        if self.running:
            self._log("A macro is already running")
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(Path(path), self._stop),
                                        name="macro", daemon=True)
        self._thread.start()

    def stop(self):
        if self.running:
            self._stop.set()

    def _run(self, path, stop):
        self._log(f"Started {path.stem}")
        try:
            run = _load(path)
            m = Macro(stop, self._log)
            m.focus()
            run(m)
            self._log(f"Finished {path.stem}")
        except MacroStopped:
            self._log(f"Stopped {path.stem}")
        except Exception:
            self._log(f"Error in {path.stem}:\n{traceback.format_exc(limit=-3)}")
        finally:
            inputs.release_all()
