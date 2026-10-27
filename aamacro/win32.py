"""Thin ctypes wrappers for the Win32 window calls the app needs.

All coordinates are physical screen pixels: main.py makes the process
per-monitor DPI aware before anything else runs.
"""
import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass

from . import config

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

LONG_PTR = ctypes.c_ssize_t
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SW_RESTORE = 9
GA_ROOT = 2
MONITOR_DEFAULTTONEAREST = 2
DWMWA_EXTENDED_FRAME_BOUNDS = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
VK_LBUTTON = 0x01
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x2


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _sig(fn, restype, *argtypes):
    fn.restype = restype
    fn.argtypes = argtypes


_sig(user32.EnumWindows, wintypes.BOOL, WNDENUMPROC, wintypes.LPARAM)
_sig(user32.GetWindowTextLengthW, ctypes.c_int, wintypes.HWND)
_sig(user32.GetWindowTextW, ctypes.c_int, wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
_sig(user32.IsWindowVisible, wintypes.BOOL, wintypes.HWND)
_sig(user32.IsWindow, wintypes.BOOL, wintypes.HWND)
_sig(user32.IsIconic, wintypes.BOOL, wintypes.HWND)
_sig(user32.IsZoomed, wintypes.BOOL, wintypes.HWND)
_sig(user32.GetWindowThreadProcessId, wintypes.DWORD, wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_sig(user32.GetClientRect, wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.RECT))
_sig(user32.GetWindowRect, wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.RECT))
_sig(user32.ClientToScreen, wintypes.BOOL, wintypes.HWND, ctypes.POINTER(wintypes.POINT))
_sig(user32.SetWindowPos, wintypes.BOOL, wintypes.HWND, wintypes.HWND,
     ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
_sig(user32.ShowWindow, wintypes.BOOL, wintypes.HWND, ctypes.c_int)
_sig(user32.SetForegroundWindow, wintypes.BOOL, wintypes.HWND)
_sig(user32.GetForegroundWindow, wintypes.HWND)
_sig(user32.MonitorFromWindow, wintypes.HMONITOR, wintypes.HWND, wintypes.DWORD)
_sig(user32.GetMonitorInfoW, wintypes.BOOL, wintypes.HMONITOR, ctypes.POINTER(MONITORINFO))
_sig(user32.GetWindowLongPtrW, LONG_PTR, wintypes.HWND, ctypes.c_int)
_sig(user32.SetWindowLongPtrW, LONG_PTR, wintypes.HWND, ctypes.c_int, LONG_PTR)
_sig(user32.GetAncestor, wintypes.HWND, wintypes.HWND, wintypes.UINT)
_sig(user32.GetCursorPos, wintypes.BOOL, ctypes.POINTER(wintypes.POINT))
_sig(user32.GetAsyncKeyState, ctypes.c_short, ctypes.c_int)
_sig(user32.keybd_event, None, wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t)
_sig(kernel32.OpenProcess, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_sig(kernel32.QueryFullProcessImageNameW, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
     wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
_sig(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
_sig(dwmapi.DwmGetWindowAttribute, ctypes.c_long, wintypes.HWND, wintypes.DWORD,
     ctypes.c_void_p, wintypes.DWORD)


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self):
        return self.left + self.width

    @property
    def bottom(self):
        return self.top + self.height

    @classmethod
    def from_win(cls, r):
        return cls(r.left, r.top, r.right - r.left, r.bottom - r.top)


def enable_dpi_awareness():
    """Make every Win32/mss/Tk coordinate a real physical pixel."""
    try:
        fn = user32.SetProcessDpiAwarenessContext
        fn.argtypes = [ctypes.c_void_p]
        if fn(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
            return
    except AttributeError:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def window_title(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_pid(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def process_name(hwnd):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, window_pid(hwnd))
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value)
    finally:
        kernel32.CloseHandle(handle)


def find_roblox_window():
    """Return the HWND of the Roblox player window, or None."""
    candidates = []

    def collect(hwnd, _):
        if user32.IsWindowVisible(hwnd) and window_title(hwnd) == config.ROBLOX_TITLE:
            candidates.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(collect), 0)
    for hwnd in candidates:
        if process_name(hwnd).lower() in config.ROBLOX_PROCESSES:
            return hwnd
    return None


def is_window(hwnd):
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def is_minimized(hwnd):
    return bool(user32.IsIconic(hwnd))


def client_rect(hwnd):
    """The window's drawable area (no title bar/borders) in screen pixels."""
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return Rect(origin.x, origin.y, r.right, r.bottom)


def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return Rect.from_win(r)


def visible_bounds(hwnd):
    """Window rect without the invisible resize margins Windows 10/11 adds."""
    r = wintypes.RECT()
    hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                      ctypes.byref(r), ctypes.sizeof(r))
    return Rect.from_win(r) if hr == 0 else window_rect(hwnd)


def _monitor_info(hwnd):
    info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
    user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST), ctypes.byref(info))
    return info


def work_area(hwnd):
    """Usable area (minus taskbar) of the monitor the window is on."""
    return Rect.from_win(_monitor_info(hwnd).rcWork)


def is_fullscreen(hwnd):
    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    monitor = Rect.from_win(_monitor_info(hwnd).rcMonitor)
    win = window_rect(hwnd)
    covers = (win.left <= monitor.left and win.top <= monitor.top
              and win.right >= monitor.right and win.bottom >= monitor.bottom)
    return covers and not (style & WS_CAPTION)


def set_client_size(hwnd, width, height, reserve_right=0):
    """Resize a window so its client area is exactly width x height.

    The window is nudged back onto its monitor if needed, leaving
    `reserve_right` pixels free on the right for the side panel.
    """
    if user32.IsZoomed(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    win = window_rect(hwnd)
    client = client_rect(hwnd)
    new_w = width + (win.width - client.width)
    new_h = height + (win.height - client.height)
    work = work_area(hwnd)
    x = min(win.left, work.right - new_w - reserve_right)
    y = min(win.top, work.bottom - new_h)
    x, y = max(x, work.left), max(y, work.top)
    user32.SetWindowPos(hwnd, None, x, y, new_w, new_h, SWP_NOZORDER | SWP_NOACTIVATE)
    return client_rect(hwnd)


def foreground_window():
    return user32.GetForegroundWindow()


def focus(hwnd):
    """Bring a window to the front. Returns True on success."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    if user32.GetForegroundWindow() == hwnd or user32.SetForegroundWindow(hwnd):
        return True
    # Windows only lets the process that last got input change the
    # foreground window; a synthetic Alt tap counts as that input.
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    return bool(user32.SetForegroundWindow(hwnd))


def root_window(hwnd):
    return user32.GetAncestor(hwnd, GA_ROOT)


def is_own_window(hwnd):
    return bool(hwnd) and window_pid(hwnd) == os.getpid()


def make_click_through(hwnd):
    """Let mouse clicks pass straight through a window to whatever is below."""
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style)


def cursor_pos():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def left_mouse_held():
    return bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
