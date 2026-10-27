"""Keyboard and mouse output through SendInput.

Keys go out as hardware scan codes because Roblox reads raw input and ignores
virtual-key-only events. Positions here are absolute *screen* pixels; turning
frame-relative coordinates into screen ones is api.Macro's job.
"""
import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000
MAPVK_VK_TO_VSC = 0

BUTTON_FLAGS = {  # button: (down, up)
    "left": (0x0002, 0x0004),
    "right": (0x0008, 0x0010),
    "middle": (0x0020, 0x0040),
}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.restype = wintypes.UINT
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.MapVirtualKeyW.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.VkKeyScanW.restype = ctypes.c_short
user32.VkKeyScanW.argtypes = [wintypes.WCHAR]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]

KEY_NAMES = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "backspace": 0x08, "shift": 0x10, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
    "lshift": 0xA0, "rshift": 0xA1, "lctrl": 0xA2, "rctrl": 0xA3, "lalt": 0xA4, "ralt": 0xA5,
    "capslock": 0x14, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    **{f"f{n}": 0x6F + n for n in range(1, 25)},
    **{f"num{n}": 0x60 + n for n in range(10)},
}
# Keys that live on the "extended" half of the keyboard need an extra flag.
EXTENDED_VKS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0xA3, 0xA5}

_lock = threading.Lock()
_held_keys = set()
_held_buttons = set()


def vk_for(key):
    """Virtual-key code for a key name ("w", "space", "f1", "shift", ...)."""
    name = key.lower()
    if name in KEY_NAMES:
        return KEY_NAMES[name]
    if len(key) == 1:
        code = user32.VkKeyScanW(key)
        if code != -1:
            return code & 0xFF
    raise ValueError(f"Unknown key {key!r}")


def _send(*events):
    arr = (INPUT * len(events))(*events)
    sent = user32.SendInput(len(events), arr, ctypes.sizeof(INPUT))
    if sent != len(events):
        raise ctypes.WinError(ctypes.get_last_error())


def _key_event(vk, up):
    flags = KEYEVENTF_SCANCODE
    if up:
        flags |= KEYEVENTF_KEYUP
    if vk in EXTENDED_VKS:
        flags |= KEYEVENTF_EXTENDEDKEY
    scan = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    return INPUT(type=INPUT_KEYBOARD, u=_INPUTUNION(ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags)))


def _mouse_event(flags, dx=0, dy=0, data=0):
    return INPUT(type=INPUT_MOUSE, u=_INPUTUNION(
        mi=MOUSEINPUT(dx=dx, dy=dy, mouseData=data & 0xFFFFFFFF, dwFlags=flags)))


def key_down(key):
    vk = vk_for(key)
    _send(_key_event(vk, up=False))
    with _lock:
        _held_keys.add(vk)


def key_up(key):
    vk = vk_for(key)
    _send(_key_event(vk, up=True))
    with _lock:
        _held_keys.discard(vk)


def char_needs_shift(char):
    """True if typing this character needs Shift held (e.g. "A", "!")."""
    code = user32.VkKeyScanW(char)
    return code != -1 and bool(code & 0x100)


def _absolute(x, y):
    vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    return round((x - vx) * 65535 / max(vw - 1, 1)), round((y - vy) * 65535 / max(vh - 1, 1))


def move_to(x, y):
    """Put the cursor on screen pixel (x, y) in a way Roblox notices."""
    flags = MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK
    # Roblox only refreshes hover state when it sees movement, so arrive
    # from one pixel away instead of teleporting.
    _send(_mouse_event(flags, *_absolute(x + 1, y)), _mouse_event(flags, *_absolute(x, y)))
    user32.SetCursorPos(x, y)  # absolute coords are scaled; this pins the exact pixel


def move_relative(dx, dy):
    """Raw mouse movement (what turns the Roblox camera)."""
    _send(_mouse_event(MOUSEEVENTF_MOVE, dx, dy))


def button_down(button="left"):
    _send(_mouse_event(BUTTON_FLAGS[button][0]))
    with _lock:
        _held_buttons.add(button)


def button_up(button="left"):
    _send(_mouse_event(BUTTON_FLAGS[button][1]))
    with _lock:
        _held_buttons.discard(button)


def scroll(clicks):
    """Mouse wheel; positive scrolls up / zooms in."""
    _send(_mouse_event(MOUSEEVENTF_WHEEL, data=int(clicks * 120)))


def release_all():
    """Let go of every key and button a macro left held down."""
    with _lock:
        keys, buttons = list(_held_keys), list(_held_buttons)
        _held_keys.clear()
        _held_buttons.clear()
    for vk in keys:
        _send(_key_event(vk, up=True))
    for button in buttons:
        _send(_mouse_event(BUTTON_FLAGS[button][1]))
