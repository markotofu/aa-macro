"""Tk UI: the border that hugs the Roblox game area, the side panel, and the image capture tool."""
import base64
import os
import queue
import re
import time
import tkinter as tk
from datetime import datetime
from tkinter import simpledialog, ttk

import cv2

from . import config, inputs, vision, win32
from .hotkeys import HotkeyListener
from .runner import MacroRunner, list_macros

BG = "#1e1f24"
FIELD = "#2a2c33"
FG = "#e6e6e6"
MUTED = "#9aa0aa"
OK = "#3ecf6e"
WARN = "#f0a43a"
KEY_COLOR = "#ff00fe"  # overlay pixels of this colour are see-through
PANEL_GAP = 6
TICK_MS = 50
LOG_LINES = 300


def _photo(img):
    ok, data = cv2.imencode(".png", img)
    return tk.PhotoImage(data=base64.b64encode(data.tobytes()).decode())


class FrameOverlay:
    """A click-through coloured border drawn just outside the Roblox game area."""

    def __init__(self, root):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=KEY_COLOR)
        self.win.attributes("-topmost", True)
        self.win.attributes("-transparentcolor", KEY_COLOR)
        self.canvas = tk.Canvas(self.win, bg=KEY_COLOR, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.rect = self.canvas.create_rectangle(0, 0, 0, 0, outline=OK, width=config.BORDER)
        self.visible = True
        self.geometry = None
        self.color = OK
        self.hide()

    def show(self, client, color):
        b = config.BORDER
        geometry = (client.left - b, client.top - b, client.width + 2 * b, client.height + 2 * b)
        if not self.visible:
            self.win.deiconify()
            self.win.update_idletasks()
            win32.make_click_through(win32.root_window(self.win.winfo_id()))
            self.visible = True
        if geometry != self.geometry:
            x, y, w, h = geometry
            self.win.geometry(f"{w}x{h}+{x}+{y}")
            self.canvas.coords(self.rect, b / 2, b / 2, w - b / 2, h - b / 2)
            self.geometry = geometry
        if color != self.color:
            self.canvas.itemconfigure(self.rect, outline=color)
            self.color = color

    def hide(self):
        if self.visible:
            self.win.withdraw()
            self.visible = False


class CaptureTool:
    """Freezes the frame on screen and lets the user drag out a region to save as an image."""

    def __init__(self, app, client, image):
        self.app = app
        self.image = image
        self.start = None
        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(f"{client.width}x{client.height}+{client.left}+{client.top}")
        self.photo = _photo(image)
        c = self.canvas = tk.Canvas(self.win, width=client.width, height=client.height,
                                    highlightthickness=0, bd=0, cursor="crosshair")
        c.pack()
        c.create_image(0, 0, anchor="nw", image=self.photo)
        hint = c.create_text(client.width // 2, 18, fill=FG, font=("Segoe UI", 11, "bold"),
                             text="Drag around what the macro should look for   ·   Esc to cancel")
        x0, y0, x1, y1 = c.bbox(hint)
        self.hint = (c.create_rectangle(x0 - 10, y0 - 5, x1 + 10, y1 + 5, fill=BG, outline=""), hint)
        c.tag_raise(hint)
        self.box = c.create_rectangle(0, 0, 0, 0, outline=OK, width=2, state="hidden")
        self.label = c.create_text(0, 0, anchor="sw", fill=OK, font=("Consolas", 9), state="hidden")
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._drag)
        c.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.focus_force()

    def _clamp(self, event):
        h, w = self.image.shape[:2]
        return min(max(event.x, 0), w), min(max(event.y, 0), h)

    def _press(self, event):
        self.start = self._clamp(event)
        for item in self.hint:
            self.canvas.itemconfigure(item, state="hidden")
        self.canvas.itemconfigure(self.box, state="normal")
        self.canvas.itemconfigure(self.label, state="normal")
        self._drag(event)

    def _drag(self, event):
        if not self.start:
            return
        (x0, y0), (x1, y1) = self.start, self._clamp(event)
        self.canvas.coords(self.box, x0, y0, x1, y1)
        self.canvas.coords(self.label, min(x0, x1), min(y0, y1) - 3)
        self.canvas.itemconfigure(self.label, text=f"({min(x0, x1)}, {min(y0, y1)})  "
                                                   f"{abs(x1 - x0)}x{abs(y1 - y0)}")

    def _release(self, event):
        if not self.start:
            return
        (x0, y0), (x1, y1) = self.start, self._clamp(event)
        self.start = None
        x, y, w, h = min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)
        if w < 4 or h < 4:
            return
        name = simpledialog.askstring(
            "Save image", f"Region ({x}, {y}, {w}, {h})\n\nSave as images/<name>.png. Name:",
            parent=self.win)
        name = re.sub(r"[^\w\-]+", "_", (name or "").strip()).strip("_")
        if not name:
            return  # cancelled: let them drag again
        vision.write_image(config.IMAGES_DIR / f"{name}.png", self.image[y:y + h, x:x + w])
        self.app.log(f'Saved images/{name}.png\n  find_image("{name}")  region=({x}, {y}, {w}, {h})')
        self.close()

    def close(self):
        self.win.destroy()


class App:
    def __init__(self):
        for folder in (config.MACROS_DIR, config.IMAGES_DIR, config.SCREENSHOTS_DIR):
            folder.mkdir(exist_ok=True)
        self.root = tk.Tk()
        self.root.title("AA Macro")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        self.events = queue.Queue()
        self.runner = MacroRunner(self.log)
        self.hwnd = None
        self.client = None
        self._next_search = 0.0
        self._snapped_hwnd = None   # window we already auto-snapped once
        self._unsnappable = None    # size Roblox refused to leave; don't auto-retry while stuck there
        self._mismatch_since = None
        self._topmost = True
        self._panel_pos = None
        self._status = None
        self._mouse_text = None
        self._last_error = None
        self._macro_paths = {}

        self._build_panel()
        self.overlay = FrameOverlay(self.root)
        self.root.geometry("+80+80")

        self.hotkeys = HotkeyListener({
            config.HOTKEY_RUN: lambda: self.events.put(("toggle",)),
            config.HOTKEY_STOP: self.runner.stop,
            config.HOTKEY_EXIT: self.emergency_exit,
        }, self.log)
        self.hotkeys.start()
        self.log(f"{config.HOTKEY_RUN.upper()} run/stop, {config.HOTKEY_STOP.upper()} stop, "
                 f"{config.HOTKEY_EXIT.upper()} exit")
        self.root.after(TICK_MS, self._tick)

    # --------------------------------------------------------------- panel

    def _build_panel(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=FG, font=("Segoe UI", 9))
        style.configure("TButton", background="#2f323a", foreground=FG, borderwidth=0,
                        focusthickness=0, padding=(8, 5))
        style.map("TButton", background=[("disabled", "#26282e"), ("active", "#3b3f49")],
                  foreground=[("disabled", "#5c6068")])
        style.configure("Accent.TButton", background="#2f6fde")
        style.map("Accent.TButton", background=[("disabled", "#26282e"), ("active", "#3a7cf0")])
        style.configure("Danger.TButton", background="#6e2b2b")
        style.map("Danger.TButton", background=[("active", "#8a3434")])
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("Head.TLabel", font=("Segoe UI Semibold", 12))
        style.configure("Section.TLabel", foreground=MUTED, font=("Segoe UI Semibold", 8))
        style.configure("TCombobox", fieldbackground=FIELD, background="#2f323a", foreground=FG,
                        arrowcolor=FG, borderwidth=0)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)],
                  selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)])
        style.configure("TSeparator", background="#33363e")
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)

        body = ttk.Frame(self.root, padding=10)
        body.pack(fill="both", expand=True)

        def section(text):
            ttk.Separator(body).pack(fill="x", pady=(10, 6))
            ttk.Label(body, text=text.upper(), style="Section.TLabel").pack(anchor="w", pady=(0, 4))

        def row():
            frame = ttk.Frame(body)
            frame.pack(fill="x", pady=2)
            return frame

        ttk.Label(body, text="AA Macro", style="Head.TLabel").pack(anchor="w")
        ttk.Label(body, text=f"Frame {config.FRAME_WIDTH} x {config.FRAME_HEIGHT}",
                  foreground=MUTED).pack(anchor="w")
        self.status_label = tk.Label(body, bg=BG, fg=WARN, justify="left", anchor="w",
                                     wraplength=210, font=("Segoe UI", 9))
        self.status_label.pack(fill="x", pady=(6, 4))
        ttk.Button(body, text="Snap to Roblox", command=self.snap).pack(fill="x", pady=2)
        self.lock_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(body, text="Keep size locked", variable=self.lock_var).pack(anchor="w", pady=2)

        section("Macro")
        self.macro_var = tk.StringVar()
        self.macro_box = ttk.Combobox(body, textvariable=self.macro_var, state="readonly",
                                      width=28, postcommand=self._refresh_macros)
        self.macro_box.pack(fill="x", pady=2)
        buttons = row()
        self.run_button = ttk.Button(buttons, text=f"Run ({config.HOTKEY_RUN.upper()})",
                                     style="Accent.TButton", command=self.run_selected)
        self.run_button.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.stop_button = ttk.Button(buttons, text=f"Stop ({config.HOTKEY_STOP.upper()})",
                                      command=self.runner.stop)
        self.stop_button.pack(side="left", fill="x", expand=True, padx=(2, 0))

        section("Tools")
        ttk.Button(body, text="Capture image…", command=self.capture_image).pack(fill="x", pady=2)
        ttk.Button(body, text="Save screenshot", command=self.save_screenshot).pack(fill="x", pady=2)
        folders = row()
        ttk.Button(folders, text="macros/", command=lambda: os.startfile(config.MACROS_DIR)) \
            .pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(folders, text="images/", command=lambda: os.startfile(config.IMAGES_DIR)) \
            .pack(side="left", fill="x", expand=True, padx=(2, 0))
        readout = row()
        self.swatch = tk.Label(readout, bg=FIELD, width=2)
        self.swatch.pack(side="left", fill="y", padx=(0, 6))
        self.mouse_label = tk.Label(readout, bg=BG, fg=FG, justify="left", anchor="w",
                                    font=("Consolas", 9))
        self.mouse_label.pack(side="left", fill="x")

        section("Log")
        self.log_text = tk.Text(body, height=10, width=30, bg="#15161a", fg=FG, bd=0,
                                font=("Consolas", 8), wrap="word", state="disabled",
                                highlightthickness=0, padx=6, pady=4)
        self.log_text.pack(fill="both", expand=True, pady=2)

        ttk.Button(body, text=f"Exit ({config.HOTKEY_EXIT.upper()})", style="Danger.TButton",
                   command=self.exit_app).pack(fill="x", pady=(8, 0))
        self._refresh_macros()

    def _refresh_macros(self):
        self._macro_paths = {p.stem: p for p in list_macros(config.MACROS_DIR)}
        names = list(self._macro_paths)
        self.macro_box["values"] = names
        if self.macro_var.get() not in self._macro_paths:
            self.macro_var.set(names[0] if names else "")

    def _set_status(self, text, color):
        if (text, color) != self._status:
            self.status_label.configure(text=text, fg=color)
            self._status = (text, color)

    def log(self, message):
        """Thread-safe: queue a line for the panel's log."""
        try:
            print(message, flush=True)
        except (AttributeError, OSError, UnicodeError):  # no/limited console (e.g. pythonw)
            pass
        self.events.put(("log", message))

    def _append_log(self, message):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{stamp} {message}\n")
        overflow = int(self.log_text.index("end-1c").split(".")[0]) - LOG_LINES
        if overflow > 0:
            self.log_text.delete("1.0", f"{overflow + 1}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------- actions

    def snap(self):
        """Resize Roblox so its game area is exactly the frame size."""
        if not self.hwnd:
            self.log("Roblox window not found")
            return
        if win32.is_fullscreen(self.hwnd):
            self.log("Roblox is fullscreen. Press F11 in Roblox first.")
            return
        self._snapped_hwnd = self.hwnd
        self._mismatch_since = None
        self.root.update_idletasks()
        client = win32.set_client_size(self.hwnd, config.FRAME_WIDTH, config.FRAME_HEIGHT,
                                       reserve_right=self.root.winfo_width() + PANEL_GAP)
        size = (client.width, client.height)
        if size == (config.FRAME_WIDTH, config.FRAME_HEIGHT):
            self._unsnappable = None
            self.log(f"Snapped Roblox to {size[0]}x{size[1]}")
        else:
            self._unsnappable = size
            self.log(f"Roblox stayed at {size[0]}x{size[1]}. It may not allow "
                     f"{config.FRAME_WIDTH}x{config.FRAME_HEIGHT}; change FRAME_WIDTH/HEIGHT "
                     "in aamacro/config.py.")

    def run_selected(self):
        path = self._macro_paths.get(self.macro_var.get())
        if not path:
            self.log("Pick a macro first (files in macros/)")
        elif not self.hwnd:
            self.log("Roblox window not found")
        else:
            self.runner.start(path)

    def toggle_run(self):
        if self.runner.running:
            self.runner.stop()
        else:
            self.run_selected()

    def capture_image(self):
        if not self.client:
            self.log("Roblox window not found")
            return
        CaptureTool(self, self.client, vision.grab(self.client))

    def save_screenshot(self):
        if not self.client:
            self.log("Roblox window not found")
            return
        path = config.SCREENSHOTS_DIR / datetime.now().strftime("frame_%Y%m%d_%H%M%S.png")
        vision.write_image(path, vision.grab(self.client))
        self.log(f"Saved screenshots/{path.name}")

    def exit_app(self):
        self.runner.stop()
        inputs.release_all()
        self.hotkeys.stop()
        self.root.destroy()

    def emergency_exit(self):
        """Exit hotkey. Runs on the hotkey thread so it works even if the UI is stuck."""
        self.runner.stop()
        try:
            inputs.release_all()
        finally:
            os._exit(0)

    # ---------------------------------------------------------------- loop

    def _tick(self):
        try:
            self._drain_events()
            self._track_roblox()
            self._update_mouse_readout()
            running = self.runner.running
            self.run_button.state(["disabled"] if running else ["!disabled"])
            self.stop_button.state(["!disabled"] if running else ["disabled"])
        except Exception as exc:  # keep the UI alive; report each distinct error once
            if repr(exc) != self._last_error:
                self._last_error = repr(exc)
                self.log(f"UI error: {exc!r}")
        finally:
            self.root.after(TICK_MS, self._tick)

    def _drain_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            if event[0] == "log":
                self._append_log(event[1])
            elif event[0] == "toggle":
                self.toggle_run()

    def _track_roblox(self):
        now = time.monotonic()
        if self.hwnd and not win32.is_window(self.hwnd):
            self.hwnd = None
            self.log("Roblox window closed")
        if not self.hwnd and now >= self._next_search:
            self._next_search = now + 1.0
            self.hwnd = win32.find_roblox_window()
            if self.hwnd:
                self.log("Found Roblox")
                self._unsnappable = None
        self.client = None

        if not self.hwnd:
            return self._detach("Waiting for Roblox… open the game.")
        if win32.is_minimized(self.hwnd):
            return self._detach("Roblox is minimized.")
        if win32.is_fullscreen(self.hwnd):
            return self._detach("Roblox is fullscreen. Press F11 in Roblox so the frame can size it.")

        client = win32.client_rect(self.hwnd)
        target = (config.FRAME_WIDTH, config.FRAME_HEIGHT)
        size = (client.width, client.height)
        if size == target:
            self._mismatch_since = None
            self._set_status(f"Snapped · game area {size[0]} x {size[1]}", OK)
        else:
            self._mismatch_since = self._mismatch_since or now
            first_time = self._snapped_hwnd != self.hwnd
            drifted = (self.lock_var.get() and now - self._mismatch_since > 0.75
                       and not win32.left_mouse_held())  # don't fight a resize drag
            if (first_time or drifted) and size != self._unsnappable:
                self.snap()
                return
            self._set_status(f"Game area is {size[0]} x {size[1]}, needs "
                             f"{target[0]} x {target[1]}. Press Snap.", WARN)
        self.client = client
        self._place(client, OK if size == target else WARN)

    def _detach(self, status):
        self._set_status(status, WARN)
        self.overlay.hide()
        self._set_topmost(True)

    def _place(self, client, color):
        foreground = win32.foreground_window()
        active = foreground == self.hwnd or win32.is_own_window(foreground)
        if active:
            self.overlay.show(client, color)
        else:
            self.overlay.hide()  # don't float over other apps
        self._set_topmost(active)

        bounds = win32.visible_bounds(self.hwnd)
        work = win32.work_area(self.hwnd)
        width, height = self.root.winfo_width(), self.root.winfo_height()
        x = bounds.right + PANEL_GAP
        if x + width > work.right:
            x = bounds.left - PANEL_GAP - width
            if x < work.left:
                x = work.right - width
        y = max(work.top, min(bounds.top, work.bottom - height))
        if (x, y) != self._panel_pos:
            self.root.geometry(f"+{x}+{y}")
            self._panel_pos = (x, y)

    def _set_topmost(self, topmost):
        if topmost != self._topmost:
            self.root.attributes("-topmost", topmost)
            self._topmost = topmost

    def _update_mouse_readout(self):
        text, color = "Mouse  —", FIELD
        if self.client:
            sx, sy = win32.cursor_pos()
            x, y = sx - self.client.left, sy - self.client.top
            if 0 <= x < self.client.width and 0 <= y < self.client.height:
                b, g, r = (int(v) for v in vision.grab(win32.Rect(sx, sy, 1, 1))[0, 0])
                text = f"Mouse  {x}, {y}\nRGB    {r}, {g}, {b}"
                color = f"#{r:02x}{g:02x}{b:02x}"
            else:
                text = "Mouse  outside frame"
        if text != self._mouse_text:
            self.mouse_label.configure(text=text)
            self.swatch.configure(bg=color)
            self._mouse_text = text

    def run(self):
        self.root.mainloop()
