"""The `m` object every macro's run(m) receives. See MACROS.md for a guide.

Every coordinate is a pixel inside the fixed-size frame: (0, 0) is the
top-left of the Roblox game area and (FRAME_WIDTH-1, FRAME_HEIGHT-1) the
bottom-right, no matter where the window is or how big the monitor is.
"""
import time
from dataclasses import dataclass
from datetime import datetime

from . import config, inputs, vision, win32


class MacroStopped(Exception):
    """Raised inside a macro when the user presses Stop; ends the macro."""


@dataclass(frozen=True)
class Match:
    """Where an image was found, in frame coordinates."""
    name: str
    x: int
    y: int
    width: int
    height: int
    score: float

    @property
    def center(self):
        return self.x + self.width // 2, self.y + self.height // 2


class Macro:
    def __init__(self, stop_event, log):
        self._stop = stop_event
        self._log = log
        self._hwnd = None
        self._warned_size = False
        self.width = config.FRAME_WIDTH
        self.height = config.FRAME_HEIGHT

    # ------------------------------------------------------------ plumbing

    def check(self):
        """Raise MacroStopped if Stop was pressed. Call it inside long pure-Python loops."""
        if self._stop.is_set():
            raise MacroStopped()

    @property
    def stopped(self):
        return self._stop.is_set()

    def _frame(self):
        self.check()
        if not win32.is_window(self._hwnd):
            self._hwnd = win32.find_roblox_window()
            if not self._hwnd:
                raise RuntimeError("Roblox window not found")
        rect = win32.client_rect(self._hwnd)
        if (rect.width, rect.height) != (self.width, self.height) and not self._warned_size:
            self._warned_size = True
            self.log(f"Warning: frame is {rect.width}x{rect.height}, expected "
                     f"{self.width}x{self.height}. Press Snap so coordinates line up.")
        return rect

    def _point(self, x, y=None):
        if isinstance(x, Match):
            x, y = x.center
        elif y is None:
            x, y = x
        x, y = int(round(x)), int(round(y))
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"({x}, {y}) is outside the {self.width}x{self.height} frame")
        return x, y

    def _to_screen(self, x, y=None):
        x, y = self._point(x, y)
        frame = self._frame()
        return frame.left + x, frame.top + y

    def _region(self, region):
        """Clamp an (x, y, w, h) frame region; None means the whole frame."""
        if region is None:
            return 0, 0, self.width, self.height
        x, y, w, h = (int(v) for v in region)
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.width, x + w), min(self.height, y + h)
        if x1 <= x0 or y1 <= y0:
            raise ValueError(f"Region {region} is outside the frame")
        return x0, y0, x1 - x0, y1 - y0

    # ------------------------------------------------------------- general

    def log(self, *parts):
        """Print a line to the panel's log."""
        self._log(" ".join(str(p) for p in parts))

    def wait(self, seconds):
        """Sleep, but wake up immediately if Stop is pressed."""
        end = time.monotonic() + seconds
        while True:
            self.check()
            left = end - time.monotonic()
            if left <= 0:
                return
            self._stop.wait(min(left, 0.05))

    def wait_until(self, condition, timeout=10, interval=0.1):
        """Poll condition() until it is truthy. Returns its value, or None on timeout."""
        end = time.monotonic() + timeout
        while True:
            result = condition()
            if result:
                return result
            if time.monotonic() >= end:
                return None
            self.wait(interval)

    def focus(self):
        """Bring Roblox to the front (done automatically when a macro starts)."""
        self._frame()
        if not win32.focus(self._hwnd):
            self.log("Warning: could not bring Roblox to the front")
        self.wait(0.1)

    # --------------------------------------------------------------- mouse

    def move(self, x, y=None):
        """Move the cursor to a frame point. Accepts x, y / (x, y) / a Match."""
        inputs.move_to(*self._to_screen(x, y))

    def mouse_position(self):
        """Cursor position in frame coordinates, or None if it is outside the frame."""
        sx, sy = win32.cursor_pos()
        frame = self._frame()
        x, y = sx - frame.left, sy - frame.top
        return (x, y) if 0 <= x < self.width and 0 <= y < self.height else None

    def click(self, x=None, y=None, button="left", clicks=1, interval=0.08):
        """Click at a frame point (or where the cursor already is if no point given)."""
        if x is not None:
            self.move(x, y)
            self.wait(0.03)
        for i in range(clicks):
            if i:
                self.wait(interval)
            self.mouse_down(button)
            self.wait(0.03)
            self.mouse_up(button)

    def double_click(self, x=None, y=None):
        self.click(x, y, clicks=2)

    def right_click(self, x=None, y=None):
        self.click(x, y, button="right")

    def mouse_down(self, button="left"):
        self.check()
        inputs.button_down(button)

    def mouse_up(self, button="left"):
        inputs.button_up(button)

    def drag(self, start, end, duration=0.3, button="left"):
        """Press at start, glide to end, release. Points are (x, y) or Matches."""
        x0, y0 = self._point(start)
        x1, y1 = self._point(end)
        self.move(x0, y0)
        self.mouse_down(button)
        try:
            steps = max(1, int(duration / 0.015))
            for i in range(1, steps + 1):
                t = i / steps
                self.move(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
                self.wait(duration / steps)
        finally:
            self.mouse_up(button)

    def move_by(self, dx, dy, duration=0.0):
        """Raw relative mouse movement, e.g. to turn the camera (hold right button first).

        Not clamped to the frame: Roblox reads it as motion, not a position.
        Windows "Enhance pointer precision" scales these moves.
        """
        steps = max(1, int(duration / 0.01))
        done_x = done_y = 0
        for i in range(1, steps + 1):
            step_x = round(dx * i / steps) - done_x
            step_y = round(dy * i / steps) - done_y
            self.check()
            inputs.move_relative(step_x, step_y)
            done_x += step_x
            done_y += step_y
            if steps > 1:
                self.wait(duration / steps)

    def scroll(self, clicks):
        """Mouse wheel. Positive = up / zoom in, negative = down / zoom out."""
        self.check()
        inputs.scroll(clicks)

    # ------------------------------------------------------------ keyboard

    def press(self, key, hold=0.05):
        """Tap a key, holding it for `hold` seconds (e.g. press("w", hold=2) walks)."""
        self.key_down(key)
        try:
            self.wait(hold)
        finally:
            self.key_up(key)

    def key_down(self, key):
        self.check()
        inputs.key_down(key)

    def key_up(self, key):
        inputs.key_up(key)

    def hotkey(self, *keys, hold=0.05):
        """Press keys together, e.g. hotkey("shift", "w")."""
        pressed = []
        try:
            for key in keys:
                self.key_down(key)
                pressed.append(key)
            self.wait(hold)
        finally:
            for key in reversed(pressed):
                self.key_up(key)

    def type(self, text, interval=0.03):
        """Type text, e.g. into the chat box (open it with press("/") first)."""
        for char in text:
            key = {"\n": "enter", "\t": "tab", " ": "space"}.get(char, char)
            if inputs.char_needs_shift(char):
                self.hotkey("shift", key, hold=0.02)
            else:
                self.press(key, hold=0.02)
            self.wait(interval)

    # -------------------------------------------------------------- vision

    def screenshot(self, region=None):
        """BGR numpy image of the frame (or an (x, y, w, h) region of it)."""
        frame = self._frame()
        x, y, w, h = self._region(region)
        return vision.grab(win32.Rect(frame.left + x, frame.top + y, w, h))

    def save_screenshot(self, name=None):
        """Save the frame to screenshots/<name>.png and return the path."""
        name = name or datetime.now().strftime("frame_%Y%m%d_%H%M%S")
        path = config.SCREENSHOTS_DIR / f"{name}.png"
        vision.write_image(path, self.screenshot())
        self.log(f"Saved {path.relative_to(config.ROOT_DIR)}")
        return path

    def _image_path(self, name):
        path = config.IMAGES_DIR / name
        if not path.suffix:
            path = path.with_suffix(".png")
        if not path.exists():
            raise FileNotFoundError(f"images/{path.name} not found. "
                                    "Make it with the panel's 'Capture image' button.")
        return path

    def _search(self, name, shot, region, confidence):
        x0, y0, w, h = self._region(region)
        template = vision.load_template(self._image_path(name))
        hit = vision.match_best(shot[y0:y0 + h, x0:x0 + w], template,
                                confidence or config.DEFAULT_CONFIDENCE)
        if not hit:
            return None
        th, tw = template.shape[:2]
        return Match(name, x0 + hit[0], y0 + hit[1], tw, th, hit[2])

    def find_image(self, name, region=None, confidence=None):
        """Look once for images/<name>.png. Returns a Match or None."""
        return self._search(name, self.screenshot(), region, confidence)

    def image_exists(self, name, region=None, confidence=None):
        return self.find_image(name, region, confidence) is not None

    def find_all_images(self, name, region=None, confidence=None):
        """Every non-overlapping place the image appears, best match first."""
        x0, y0, w, h = self._region(region)
        template = vision.load_template(self._image_path(name))
        th, tw = template.shape[:2]
        hits = vision.match_all(self.screenshot()[y0:y0 + h, x0:x0 + w], template,
                                confidence or config.DEFAULT_CONFIDENCE)
        return [Match(name, x0 + x, y0 + y, tw, th, s) for x, y, s in hits]

    def wait_for_image(self, name, timeout=10, region=None, confidence=None, interval=0.1):
        """Keep looking until the image appears. Returns a Match, or None on timeout."""
        return self.wait_until(lambda: self.find_image(name, region, confidence), timeout, interval)

    def wait_for_image_gone(self, name, timeout=10, region=None, confidence=None, interval=0.1):
        """Wait until the image is no longer on screen. Returns True if it went away."""
        return bool(self.wait_until(lambda: not self.image_exists(name, region, confidence),
                                    timeout, interval))

    def click_image(self, name, timeout=0, region=None, confidence=None, offset=(0, 0)):
        """Click the centre of an image (waiting up to `timeout` s). Returns the Match or None."""
        match = self.wait_for_image(name, timeout, region, confidence) if timeout \
            else self.find_image(name, region, confidence)
        if match:
            cx, cy = match.center
            self.click(cx + offset[0], cy + offset[1])
        return match

    def wait_for_any(self, options, timeout=10, region=None, confidence=None, interval=0.1):
        """Wait until one of several things shows up, so the macro can branch.

        options maps a label to an image name or to a zero-argument function:
            outcome, match = m.wait_for_any({"win": "victory", "lose": "defeat"}, timeout=120)
        Returns (label, Match-or-True) for the first one seen, or (None, None) on timeout.
        """
        if not isinstance(options, dict):
            options = {name: name for name in options}

        def poll():
            shot = self.screenshot()
            for label, target in options.items():
                found = target() if callable(target) else self._search(target, shot, region, confidence)
                if found:
                    return label, found
            return None

        return self.wait_until(poll, timeout, interval) or (None, None)

    def pixel(self, x, y=None):
        """(r, g, b) colour of one frame pixel."""
        x, y = self._point(x, y)
        b, g, r = self.screenshot((x, y, 1, 1))[0, 0]
        return int(r), int(g), int(b)

    def color_matches(self, x, y, rgb, tolerance=10):
        """True if the pixel at (x, y) is within `tolerance` of rgb on each channel."""
        return all(abs(a - b) <= tolerance for a, b in zip(self.pixel(x, y), rgb))

    def find_color(self, rgb, region=None, tolerance=10):
        """Frame (x, y) of the first pixel with this colour, or None."""
        x0, y0, _, _ = self._region(region)
        hit = vision.find_color(self.screenshot(region), rgb, tolerance)
        return (x0 + hit[0], y0 + hit[1]) if hit else None

    def wait_for_color(self, x, y, rgb, tolerance=10, timeout=10, interval=0.1):
        """Wait until pixel (x, y) turns this colour. Returns True if it did."""
        return bool(self.wait_until(lambda: self.color_matches(x, y, rgb, tolerance), timeout, interval))
