"""System-wide hotkeys via RegisterHotKey, so they work while Roblox has focus."""
import ctypes
import threading
from ctypes import wintypes

from .inputs import vk_for

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

user32.RegisterHotKey.restype = wintypes.BOOL
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]


class HotkeyListener(threading.Thread):
    """Calls bindings[key]() on this thread whenever that key is pressed anywhere."""

    def __init__(self, bindings, log):
        super().__init__(name="hotkeys", daemon=True)
        self._bindings = dict(bindings)
        self._log = log
        self._thread_id = None

    def run(self):
        # Hotkeys belong to the thread that registers them, so register here.
        self._thread_id = kernel32.GetCurrentThreadId()
        callbacks = {}
        for hotkey_id, (key, callback) in enumerate(self._bindings.items(), start=1):
            if user32.RegisterHotKey(None, hotkey_id, MOD_NOREPEAT, vk_for(key)):
                callbacks[hotkey_id] = callback
            else:
                self._log(f"Could not register hotkey {key.upper()} (another app is using it)")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY and msg.wParam in callbacks:
                callbacks[msg.wParam]()
        for hotkey_id in callbacks:
            user32.UnregisterHotKey(None, hotkey_id)

    def stop(self):
        if self._thread_id:
            user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
