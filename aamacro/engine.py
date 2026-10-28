"""Plays a flow: nodes run their steps, checkers pick what's next, overseers interrupt."""
import threading

from . import config, inputs
from .api import Macro, MacroInterrupted, MacroStopped
from .flow import parse_ref, ref_label


def run_step(m, step):
    kind = step["type"]
    if kind == "key":
        m.press(step["key"], hold=step.get("hold", 0.05))
    elif kind == "delay":
        m.wait(step["seconds"])
    elif kind == "click":
        m.click(step["x"], step["y"], button=step.get("button", "left"))
    elif kind in ("click_image", "wait_image"):
        timeout = step.get("timeout", 10)
        match = m.wait_for_image(step["image"], timeout=timeout, confidence=step.get("confidence"))
        if not match:
            m.log(f'  "{step["image"]}" not seen within {timeout:g}s, skipping')
        elif kind == "click_image":
            m.click(match, button=step.get("button", "left"))
    else:
        raise ValueError(f"Unknown step type {kind!r}")


def run_node(m, flow, name):
    """Play a node's steps. Returns where to go next."""
    node = flow.nodes.get(name)
    if node is None:
        raise RuntimeError(f'Node "{name}" does not exist')
    m.log(f"Node {name}")
    for step in node["steps"]:
        run_step(m, step)
        m.wait(config.STEP_GAP)
    return node.get("next")


def run_checker(m, flow, name):
    """Look for the checker's images until one shows up or it times out. Returns where to go next."""
    checker = flow.checkers.get(name)
    if checker is None:
        raise RuntimeError(f'Checker "{name}" does not exist')
    m.log(f"Checker {name}")
    branches = checker["branches"]

    def first_seen():
        shot = m.screenshot()
        for branch in branches:
            if m.find_image_in(shot, branch["image"], confidence=branch.get("confidence")):
                return branch
        return None

    timeout = checker.get("timeout", 30)
    branch = m.wait_until(first_seen, timeout, interval=0.15) if branches else None
    if branch:
        m.log(f'  saw "{branch["image"]}" -> {ref_label(branch.get("goto"))}')
        return branch.get("goto")
    m.log(f"  nothing seen in {timeout:g}s -> {ref_label(checker.get('fallback'))}")
    return checker.get("fallback")


class OverseerWatch(threading.Thread):
    """Looks for every overseer's image a few times a second while a flow runs.

    An overseer fires once, then stays quiet until its image has gone away,
    so it can't keep re-triggering on the same screen.
    """

    def __init__(self, flow, stop, interrupt, log):
        super().__init__(name="overseers", daemon=True)
        self.flow = flow
        self.stop = stop
        self.interrupt = interrupt
        self.log = log
        self.done = threading.Event()
        self.paused = threading.Event()
        self.triggered = None
        self.armed = {name: True for name in flow.overseers}

    def run(self):
        m = Macro(self.done, self.log, self.flow.images_dir)
        try:
            while not self.stop.is_set() and not self.done.is_set():
                if not self.paused.is_set() and self.triggered is None:
                    self._look(m, m.screenshot())
                self.done.wait(config.OVERSEER_INTERVAL)
        except MacroStopped:
            pass
        except Exception as exc:
            self.log(f"Overseers stopped watching: {exc}")

    def _look(self, m, shot):
        for name, overseer in self.flow.overseers.items():
            seen = m.find_image_in(shot, overseer["image"], confidence=overseer.get("confidence"))
            if not seen:
                self.armed[name] = True
            elif self.armed[name]:
                self.armed[name] = False
                self.triggered = name
                self.interrupt.set()
                return


def run_flow(flow, stop, log, start=None, only=False):
    """Play a flow from its start (or `start`). With only=True, run just that one piece."""
    problems = flow.problems()
    if problems:
        for problem in problems:
            log(f"  ! {problem}")
        log("Fix the problems above in the editor first.")
        return
    warning = flow.frame_warning()
    if warning:
        log(f"Warning: {warning}")

    interrupt = threading.Event()
    m = Macro(stop, log, flow.images_dir, interrupt)
    m.focus()
    watch = None
    if flow.overseers and not only:
        watch = OverseerWatch(flow, stop, interrupt, log)
        watch.start()
    current = start or flow.data["start"]
    try:
        while current:
            kind, name = parse_ref(current)
            try:
                after = run_node(m, flow, name) if kind == "node" else run_checker(m, flow, name)
                current = None if only else after
            except MacroInterrupted:
                current = _handle_overseer(flow, watch, interrupt, stop, log)
    finally:
        if watch:
            watch.done.set()


def _handle_overseer(flow, watch, interrupt, stop, log):
    name = watch.triggered
    overseer = flow.overseers[name]
    interrupt.clear()
    inputs.release_all()  # the interrupted node may have been holding keys
    log(f'Overseer {name} saw "{overseer["image"]}"')
    watch.paused.set()
    try:
        if overseer.get("run"):
            run_node(Macro(stop, log, flow.images_dir), flow, overseer["run"])
    finally:
        watch.triggered = None
        watch.paused.clear()
    log(f"  then -> {ref_label(overseer.get('then'))}")
    return overseer.get("then")


def check_overseer(flow, name, stop, log):
    """Test button: is this overseer's image on screen right now?"""
    overseer = flow.overseers[name]
    if not overseer.get("image"):
        log(f'Overseer "{name}" has no image yet')
        return
    match = Macro(stop, log, flow.images_dir).find_image(overseer["image"], confidence=overseer.get("confidence"))
    if match:
        log(f'Overseer {name}: "{overseer["image"]}" IS on screen at {match.center} '
            f"(score {match.score:.2f}), would run node {overseer.get('run') or '(none)'}")
    else:
        log(f'Overseer {name}: "{overseer["image"]}" is not on screen')
