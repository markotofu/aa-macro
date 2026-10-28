"""Runs one macro job at a time on a background thread."""
import importlib.util
import threading
import traceback
from pathlib import Path

from . import engine, inputs
from .api import Macro, MacroStopped


def list_macros(folder):
    """Python macro files in the folder; names starting with "_" are hidden."""
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

    def start(self, label, job):
        """Run job(stop_event) in the background unless something is already running."""
        if self.running:
            self._log("Something is already running (F7 stops it)")
            return
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(label, job, self._stop),
                                        name="macro", daemon=True)
        self._thread.start()

    def start_script(self, path):
        path = Path(path)

        def job(stop):
            run = _load(path)
            m = Macro(stop, self._log)
            m.focus()
            run(m)
        self.start(path.stem, job)

    def start_flow(self, flow, start=None, only=False, label=None):
        self.start(label or flow.name,
                   lambda stop: engine.run_flow(flow, stop, self._log, start=start, only=only))

    def stop(self):
        if self.running:
            self._stop.set()

    def _run(self, label, job, stop):
        self._log(f"Started {label}")
        try:
            job(stop)
            self._log(f"Finished {label}")
        except MacroStopped:
            self._log(f"Stopped {label}")
        except Exception:
            self._log(f"Error in {label}:\n{traceback.format_exc(limit=-3)}")
        finally:
            inputs.release_all()
