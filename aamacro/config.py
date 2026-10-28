"""Settings shared by the whole app. Edit these to taste."""
from pathlib import Path

# The Roblox client area is always resized to exactly this many pixels, so
# every coordinate and image in a macro means the same thing on any monitor.
# 800x600 fits on even a 1366x768 laptop with room for the side panel.
FRAME_WIDTH = 800
FRAME_HEIGHT = 600

# Thickness of the coloured border drawn around the frame.
BORDER = 3

# Global hotkeys (work even while Roblox has focus).
HOTKEY_RUN = "f6"    # run / stop the selected macro
HOTKEY_STOP = "f7"   # stop the running macro
HOTKEY_EXIT = "f8"   # kill the whole app immediately

# How closely an image must match (0..1) when a macro does not say otherwise.
# Below 1.0 so small differences (lighting, animation, anti-aliasing) still match.
DEFAULT_CONFIDENCE = 0.8

# Mouse glides to its target instead of teleporting.
MOUSE_GLIDE = True
MOUSE_SPEED = 1400        # pixels per second
MOUSE_GLIDE_MIN = 0.08    # seconds
MOUSE_GLIDE_MAX = 0.6

STEP_GAP = 0.1            # pause between recorded steps when a node plays
OVERSEER_INTERVAL = 0.25  # how often overseers look at the screen

ROBLOX_TITLE = "Roblox"
ROBLOX_PROCESSES = ("robloxplayerbeta.exe", "windows10universal.exe")

ROOT_DIR = Path(__file__).resolve().parent.parent
MACROS_DIR = ROOT_DIR / "macros"
IMAGES_DIR = ROOT_DIR / "images"
SCREENSHOTS_DIR = ROOT_DIR / "screenshots"
FLOWS_DIR = ROOT_DIR / "flows"        # macros built in Create mode
LIBRARY_DIR = ROOT_DIR / "library"    # reusable nodes, one zip each
EXPORTS_DIR = ROOT_DIR / "exports"    # whole-macro zips to share
