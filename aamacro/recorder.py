"""Create mode recording: turns \\ ] [ presses in the game into node steps.

    \\  then a key   records that key (and how long you held it)
    ]               asks for a delay
    [               clicks where the cursor is and records the click

The three command keys are only grabbed while recording, so they work
normally in Roblox the rest of the time.
"""
import threading
import time

from . import inputs, win32
from .hotkeys import HotkeyListener

KEY_TIMEOUT = 10  # seconds to wait for the key after \
COMMAND_KEYS = {"\\": inputs.vk_for("\\"), "[": inputs.vk_for("["), "]": inputs.vk_for("]")}


class Recorder:
    def __init__(self, frame_rect, add_step, ask_delay, log):
        """frame_rect() -> Rect of the game area or None. add_step(step) and
        ask_delay() are called from background threads."""
        self._frame_rect = frame_rect
        self._add_step = add_step
        self._ask_delay = ask_delay
        self._log = log
        self._hotkeys = None
        self._awaiting_key = False

    @property
    def active(self):
        return self._hotkeys is not None

    def start(self):
        if self.active:
            return
        self._hotkeys = HotkeyListener({
            "\\": self._on_key_command,
            "[": self._on_click_command,
            "]": self._on_delay_command,
        }, self._log)
        self._hotkeys.start()

    def stop(self):
        if self._hotkeys:
            self._hotkeys.stop()
            self._hotkeys = None
        self._awaiting_key = False

    def _on_key_command(self):
        if self._awaiting_key:  # "\" then "\" records a backslash
            return self._record_key(COMMAND_KEYS["\\"], 0.05)
        self._awaiting_key = True
        self._log("Press the key to record…")
        threading.Thread(target=self._wait_for_key, daemon=True).start()

    def _on_click_command(self):
        if self._awaiting_key:
            return self._record_key(COMMAND_KEYS["["], 0.05)
        frame = self._frame_rect()
        if not frame:
            return self._log("Roblox not found, click not recorded")
        sx, sy = win32.cursor_pos()
        x, y = sx - frame.left, sy - frame.top
        if not (0 <= x < frame.width and 0 <= y < frame.height):
            return self._log("Cursor is outside the frame, click not recorded")
        inputs.button_down("left")
        time.sleep(0.03)
        inputs.button_up("left")
        self._add_step({"type": "click", "x": x, "y": y, "button": "left"})

    def _on_delay_command(self):
        if self._awaiting_key:
            return self._record_key(COMMAND_KEYS["]"], 0.05)
        self._ask_delay()

    def _wait_for_key(self):
        # Keys already down when "\" was pressed (e.g. still holding W) don't count.
        ignore = {vk for vk in inputs.RECORDABLE_VKS if inputs.is_pressed(vk)}
        command_vks = set(COMMAND_KEYS.values())  # these arrive as hotkeys instead
        deadline = time.monotonic() + KEY_TIMEOUT
        while self._awaiting_key and time.monotonic() < deadline:
            for vk in inputs.RECORDABLE_VKS:
                if vk in command_vks:
                    continue
                if not inputs.is_pressed(vk):
                    ignore.discard(vk)
                elif vk not in ignore:
                    started = time.monotonic()
                    while inputs.is_pressed(vk) and time.monotonic() - started < 60:
                        time.sleep(0.01)
                    return self._record_key(vk, max(0.05, round(time.monotonic() - started, 2)))
            time.sleep(0.01)
        if self._awaiting_key:
            self._awaiting_key = False
            self._log("No key pressed, nothing recorded")

    def _record_key(self, vk, hold):
        self._awaiting_key = False
        name = inputs.key_name(vk)
        if not name:
            return self._log(f"That key (code {vk}) can't be recorded")
        self._add_step({"type": "key", "key": name, "hold": hold})
