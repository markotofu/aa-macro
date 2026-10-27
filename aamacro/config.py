"""Settings shared by the whole app. Edit these to taste."""
from pathlib import Path

# The Roblox client area is always resized to exactly this many pixels, so
# every coordinate and image in a macro means the same thing on any monitor.
# 1024x576 (16:9) fits on a 1366x768 laptop with room for the side panel.
FRAME_WIDTH = 1024
FRAME_HEIGHT = 576

# Thickness of the coloured border drawn around the frame.
BORDER = 3

# Global hotkeys (work even while Roblox has focus).
HOTKEY_RUN = "f6"    # run / stop the selected macro
HOTKEY_STOP = "f7"   # stop the running macro
HOTKEY_EXIT = "f8"   # kill the whole app immediately

# How closely an image must match (0..1) when a macro does not say otherwise.
DEFAULT_CONFIDENCE = 0.85

ROBLOX_TITLE = "Roblox"
ROBLOX_PROCESSES = ("robloxplayerbeta.exe", "windows10universal.exe")

ROOT_DIR = Path(__file__).resolve().parent.parent
MACROS_DIR = ROOT_DIR / "macros"
IMAGES_DIR = ROOT_DIR / "images"
SCREENSHOTS_DIR = ROOT_DIR / "screenshots"
