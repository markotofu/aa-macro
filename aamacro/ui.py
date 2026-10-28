"""Tk UI: the border that hugs the Roblox game area and the side panel with its three modes.

  Create  build macros from nodes, checkers and overseers (opens the editor)
  Macro   run a macro
  Input   import shared zips / Python macros into the runnable list
"""
import os
import queue
import shutil
import time
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk

from . import config, engine, inputs, vision, win32
from .editor import Editor
from .flow import Flow, describe_step, import_zip, list_flows, make_ref
from .hotkeys import HotkeyListener
from .recorder import Recorder
from .runner import MacroRunner, list_macros
from .theme import BG, FG, FIELD, MUTED, OK, WARN, apply_style, listbox
from .tools import CaptureTool, PointPicker, ask_form

KEY_COLOR = "#ff00fe"  # overlay pixels of this colour are see-through
PANEL_GAP = 6
TICK_MS = 50
LOG_LINES = 300
MODES = ("create", "macro", "input")


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


class App:
    def __init__(self):
        for folder in (config.MACROS_DIR, config.IMAGES_DIR, config.SCREENSHOTS_DIR,
                       config.FLOWS_DIR, config.LIBRARY_DIR, config.EXPORTS_DIR):
            folder.mkdir(exist_ok=True)
        self.root = tk.Tk()
        self.root.title("AA Macro")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG)
        apply_style(self.root)
        self.events = queue.Queue()
        self.runner = MacroRunner(self.log)
        self.recorder = Recorder(lambda: self.client,
                                 lambda step: self.events.put(("step", step)),
                                 lambda: self.events.put(("ask_delay",)), self.log)
        self.recording = None   # (flow, node name) while recording
        self.flow = None        # macro open in Create mode
        self.editor = None
        self.mode = None
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
        self._runnables = {}

        self._build_panel()
        self.overlay = FrameOverlay(self.root)
        self.root.geometry("+80+80")
        self.set_mode("macro")

        self.hotkeys = HotkeyListener({
            config.HOTKEY_RUN: lambda: self.events.put(("f6",)),
            config.HOTKEY_STOP: lambda: self.events.put(("f7",)),
            config.HOTKEY_EXIT: self.emergency_exit,
        }, self.log)
        self.hotkeys.start()
        self.log(f"{config.HOTKEY_RUN.upper()} run/record, {config.HOTKEY_STOP.upper()} stop, "
                 f"{config.HOTKEY_EXIT.upper()} exit")
        self.root.after(TICK_MS, self._tick)

    # --------------------------------------------------------------- panel

    def _build_panel(self):
        body = ttk.Frame(self.root, padding=10)
        body.pack(fill="both", expand=True)
        self.body = body

        ttk.Label(body, text="AA Macro", style="Head.TLabel").pack(anchor="w")
        ttk.Label(body, text=f"Frame {config.FRAME_WIDTH} x {config.FRAME_HEIGHT}",
                  style="Muted.TLabel").pack(anchor="w")
        self.status_label = tk.Label(body, bg=BG, fg=WARN, justify="left", anchor="w",
                                     wraplength=220, font=("Segoe UI", 9))
        self.status_label.pack(fill="x", pady=(6, 4))
        row = self._row(body)
        ttk.Button(row, text="Snap to Roblox", command=self.snap).pack(side="left", fill="x", expand=True)
        self.lock_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Lock", variable=self.lock_var).pack(side="left", padx=(6, 0))

        ttk.Separator(body).pack(fill="x", pady=(10, 6))
        modes = self._row(body)
        self.mode_buttons = {}
        for mode in MODES:
            button = ttk.Button(modes, text=mode.title(), command=lambda m=mode: self.set_mode(m))
            button.pack(side="left", fill="x", expand=True, padx=1)
            self.mode_buttons[mode] = button
        self.mode_area = ttk.Frame(body)
        self.mode_area.pack(fill="x", pady=(6, 0))
        self.mode_frames = {"create": self._build_create(), "macro": self._build_macro(),
                            "input": self._build_input()}

        ttk.Separator(body).pack(fill="x", pady=(10, 6))
        readout = self._row(body)
        self.swatch = tk.Label(readout, bg=FIELD, width=2)
        self.swatch.pack(side="left", fill="y", padx=(0, 6))
        self.mouse_label = tk.Label(readout, bg=BG, fg=FG, justify="left", anchor="w", font=("Consolas", 9))
        self.mouse_label.pack(side="left", fill="x")
        ttk.Button(readout, text="Screenshot", command=self.save_screenshot).pack(side="right")

        self.log_text = tk.Text(body, height=8, width=34, bg="#15161a", fg=FG, bd=0,
                                font=("Consolas", 8), wrap="word", state="disabled",
                                highlightthickness=0, padx=6, pady=4)
        self.log_text.pack(fill="both", expand=True, pady=(8, 2))
        ttk.Button(body, text=f"Exit ({config.HOTKEY_EXIT.upper()})", style="Danger.TButton",
                   command=self.exit_app).pack(fill="x", pady=(6, 0))

    @staticmethod
    def _row(parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", pady=2)
        return frame

    def _build_create(self):
        frame = ttk.Frame(self.mode_area)
        ttk.Label(frame, text="Macro to edit", style="Section.TLabel").pack(anchor="w")
        self.flow_var = tk.StringVar()
        self.flow_box = ttk.Combobox(frame, textvariable=self.flow_var, state="readonly",
                                     postcommand=self._refresh_flow_box)
        self.flow_box.pack(fill="x", pady=2)
        self.flow_box.bind("<<ComboboxSelected>>", lambda e: self._open_flow(self.flow_var.get()))
        row = self._row(frame)
        ttk.Button(row, text="New macro", command=self.new_flow).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(row, text="Open editor", style="Accent.TButton", command=self.open_editor) \
            .pack(side="left", fill="x", expand=True, padx=(2, 0))
        self.record_label = tk.Label(frame, bg=BG, fg=MUTED, justify="left", anchor="w", wraplength=220,
                                     font=("Segoe UI", 9), text="Not recording")
        self.record_label.pack(fill="x", pady=(6, 0))
        ttk.Label(frame, style="Muted.TLabel", justify="left", font=("Consolas", 8), text=(
            "F6 records into the node selected\nin the editor. While recording:\n"
            "  \\ + key   key press\n  ]         delay\n  [         click at cursor")).pack(anchor="w", pady=(4, 0))
        return frame

    def _build_macro(self):
        frame = ttk.Frame(self.mode_area)
        ttk.Label(frame, text="Macro to run", style="Section.TLabel").pack(anchor="w")
        self.run_var = tk.StringVar()
        self.run_box = ttk.Combobox(frame, textvariable=self.run_var, state="readonly",
                                    postcommand=self._refresh_runnables)
        self.run_box.pack(fill="x", pady=2)
        row = self._row(frame)
        self.run_button = ttk.Button(row, text=f"Run ({config.HOTKEY_RUN.upper()})", style="Accent.TButton",
                                     command=self.run_selected)
        self.run_button.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.stop_button = ttk.Button(row, text=f"Stop ({config.HOTKEY_STOP.upper()})", command=self.runner.stop)
        self.stop_button.pack(side="left", fill="x", expand=True, padx=(2, 0))
        ttk.Button(frame, text="Capture image for .py macros…",
                   command=lambda: self.capture(config.IMAGES_DIR, lambda name, region: None)) \
            .pack(fill="x", pady=(6, 0))
        return frame

    def _build_input(self):
        frame = ttk.Frame(self.mode_area)
        row = self._row(frame)
        ttk.Button(row, text="Import zip…", style="Accent.TButton", command=self.import_zip) \
            .pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(row, text="Add .py…", command=self.add_python_macro) \
            .pack(side="left", fill="x", expand=True, padx=(2, 0))
        ttk.Label(frame, text="Runnable macros", style="Section.TLabel").pack(anchor="w", pady=(6, 2))
        self.input_list = listbox(frame, height=6)
        self.input_list.pack(fill="x")
        row = self._row(frame)
        ttk.Button(row, text="Export zip", command=self.export_selected).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(row, text="Remove", command=self.remove_selected).pack(side="left", fill="x", expand=True, padx=(2, 0))
        row = self._row(frame)
        for name, folder in (("exports/", config.EXPORTS_DIR), ("library/", config.LIBRARY_DIR)):
            ttk.Button(row, text=name, command=lambda f=folder: os.startfile(f)) \
                .pack(side="left", fill="x", expand=True, padx=1)
        return frame

    def set_mode(self, mode):
        if mode == self.mode:
            return
        if self.recording and mode != "create":
            self.stop_recording()
        self.mode = mode
        for name, frame in self.mode_frames.items():
            frame.pack_forget()
            self.mode_buttons[name].configure(style="ModeOn.TButton" if name == mode else "Mode.TButton")
        self.mode_frames[mode].pack(fill="x")
        self._refresh_runnables()
        if mode == "create":
            self._refresh_flow_box()

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

    # --------------------------------------------------------- create mode

    def _refresh_flow_box(self):
        names = [p.name for p in list_flows()]
        self.flow_box["values"] = names
        if self.flow and self.flow.name in names:
            self.flow_var.set(self.flow.name)
        elif names and not self.flow:
            self._open_flow(names[0])

    def _open_flow(self, name):
        if self.flow and self.flow.name == name:
            return
        if self.editor:
            self.editor.close()
        self.flow = Flow.load(config.FLOWS_DIR / name)
        self.flow_var.set(name)

    def new_flow(self):
        answer = ask_form(self.root, "New macro", [{"key": "name", "label": "Macro name", "value": "my_macro"}])
        if not answer:
            return
        if self.editor:
            self.editor.close()
        self.flow = Flow.create(answer["name"])
        self.flow.add("node", "start")
        self._refresh_flow_box()
        self.log(f"Created macro {self.flow.name}")
        self.open_editor()

    def open_editor(self):
        if not self.flow:
            return self.new_flow()
        if self.editor:
            self.editor.win.deiconify()
            self.editor.win.lift()
            return
        self.editor = Editor(self, self.flow)

    def toggle_recording(self, flow, node):
        if self.recording:
            self.stop_recording()
        else:
            self.start_recording(flow, node)

    def start_recording(self, flow, node):
        if self.runner.running:
            return self.log("Stop the running macro first")
        if not self.hwnd:
            return self.log("Roblox window not found")
        self.recording = (flow, node)
        self.recorder.start()
        self.log(f"Recording into node {node}")
        self._update_record_ui()
        win32.focus(self.hwnd)

    def stop_recording(self):
        if not self.recording:
            return
        flow, node = self.recording
        self.recorder.stop()
        self.recording = None
        self.log(f"Stopped recording {node}")
        if node in flow.nodes:
            self.save_node_to_library(flow, node)
        self._update_record_ui()

    def _update_record_ui(self):
        if self.recording:
            flow, node = self.recording
            self.record_label.configure(text=f"● Recording {node} ({len(flow.nodes[node]['steps'])} steps)", fg=WARN)
        else:
            self.record_label.configure(text="Not recording", fg=MUTED)
        if self.editor:
            self.editor.update_record_state()

    def _on_step(self, step):
        if not self.recording:
            return
        flow, node = self.recording
        flow.nodes[node]["steps"].append(step)
        flow.save()
        self.log(f"+ {describe_step(step)}")
        self._update_record_ui()
        if self.editor and self.editor.flow is flow:
            self.editor.on_step_recorded(node)

    def _ask_delay(self):
        if not self.recording:
            return
        answer = ask_form(self.root, "Delay", [
            {"key": "seconds", "label": "Seconds to wait", "kind": "float", "value": 1.0}])
        if answer:
            self._on_step({"type": "delay", "seconds": answer["seconds"]})
        if self.hwnd:
            win32.focus(self.hwnd)

    def save_node_to_library(self, flow, node):
        path = flow.save_node_to_library(node)
        self.log(f"Saved node to {path.parent.name}/{path.name}")

    def on_node_renamed(self, flow, old, new):
        if self.recording == (flow, old):
            self.recording = (flow, new)
            self._update_record_ui()

    def on_node_deleted(self, flow, node):
        if self.recording == (flow, node):
            self.stop_recording()

    def test_piece(self, flow, kind, name):
        """Launch one node/checker right away (or check an overseer's image)."""
        if self.recording:
            self.stop_recording()
        if not self.hwnd:
            return self.log("Roblox window not found")
        if kind == "overseer":
            self.runner.start(f"check {name}", lambda stop: engine.check_overseer(flow, name, stop, self.log))
        else:
            self.runner.start_flow(flow, start=make_ref(kind, name), only=True, label=f"test {name}")

    def _freeze_game(self, open_tool):
        """Bring Roblox above the editor, then screenshot it and open a capture/pick tool."""
        if not self.client:
            return self.log("Roblox window not found")
        win32.focus(self.hwnd)

        def opened():
            if not self.client:
                return self.log("Roblox window not found")
            tool = open_tool(self.client, vision.grab(self.client))
            tool.on_close = lambda: self.editor and self.editor.win.lift()
        self.root.after(250, opened)  # give Windows a moment to repaint the game on top

    def capture(self, images_dir, on_saved, suggested=""):
        def saved(name, region):
            self.log(f'Saved image "{name}"  region={region}')
            on_saved(name, region)
        self._freeze_game(lambda client, shot: CaptureTool(self.root, client, shot, images_dir, saved, suggested))

    def pick_point(self, on_pick):
        self._freeze_game(lambda client, shot: PointPicker(self.root, client, shot, on_pick))

    # ---------------------------------------------------------- macro mode

    def _refresh_runnables(self):
        runnables = {p.name: ("flow", p) for p in list_flows()}
        runnables.update({f"{p.stem} (python)": ("python", p) for p in list_macros(config.MACROS_DIR)})
        self._runnables = runnables
        names = list(runnables)
        self.run_box["values"] = names
        if self.run_var.get() not in runnables:
            self.run_var.set(names[0] if names else "")
        self.input_list.delete(0, "end")
        for name in names:
            self.input_list.insert("end", name)

    def run_selected(self):
        entry = self._runnables.get(self.run_var.get())
        if not entry:
            self.log("Pick a macro first")
        elif not self.hwnd:
            self.log("Roblox window not found")
        elif entry[0] == "flow":
            self.runner.start_flow(Flow.load(entry[1]))
        else:
            self.runner.start_script(entry[1])

    def run_flow(self, flow):
        if self.recording:
            self.stop_recording()
        if not self.hwnd:
            return self.log("Roblox window not found")
        flow.save()
        self.runner.start_flow(flow)

    # ---------------------------------------------------------- input mode

    def import_zip(self):
        paths = filedialog.askopenfilenames(parent=self.root, title="Import AA Macro zip",
                                            filetypes=[("AA Macro zip", "*.zip")])
        for path in paths:
            try:
                kind, name = import_zip(path)
            except Exception as exc:
                self.log(f"Import failed: {exc}")
                continue
            if kind == "flow":
                self.log(f"Imported macro {name}, ready in Macro mode")
            else:
                self.log(f"Imported node {name} into the library (editor > + From library)")
        self._refresh_runnables()

    def add_python_macro(self):
        paths = filedialog.askopenfilenames(parent=self.root, title="Add Python macro",
                                            filetypes=[("Python macro", "*.py")])
        for path in paths:
            target = config.MACROS_DIR / os.path.basename(path)
            if target.exists() and not messagebox.askyesno("Replace", f"{target.name} exists. Replace it?",
                                                           parent=self.root):
                continue
            shutil.copyfile(path, target)
            self.log(f"Added macros/{target.name}")
        self._refresh_runnables()

    def _input_selection(self):
        selection = self.input_list.curselection()
        return self._runnables.get(self.input_list.get(selection[0])) if selection else None

    def export_selected(self):
        entry = self._input_selection()
        if not entry:
            return self.log("Select a macro in the list first")
        if entry[0] != "flow":
            return self.log("Python macros are shared by copying the .py file")
        path = Flow.load(entry[1]).export_zip()
        self.log(f"Exported {path.parent.name}/{path.name}")

    def remove_selected(self):
        entry = self._input_selection()
        if not entry:
            return
        kind, path = entry
        if not messagebox.askyesno("Remove", f"Delete {path.name} from the runnable list? "
                                   "This deletes its files (export a zip first to keep a copy).",
                                   parent=self.root):
            return
        if self.flow and kind == "flow" and self.flow.folder == path:
            if self.editor:
                self.editor.close()
            self.flow = None
        if kind == "flow":
            shutil.rmtree(path)
        else:
            path.unlink()
        self.log(f"Removed {path.name}")
        self._refresh_runnables()

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

    def on_f6(self):
        if self.mode == "create":
            if self.recording:
                self.stop_recording()
            elif self.editor and self.editor.selected_node():
                self.start_recording(self.flow, self.editor.selected_node())
            else:
                self.log("Open the editor and select a node to record into")
        elif self.runner.running:
            self.runner.stop()
        else:
            self.run_selected()

    def on_f7(self):
        if self.recording:
            self.stop_recording()
        self.runner.stop()

    def save_screenshot(self):
        if not self.client:
            self.log("Roblox window not found")
            return
        path = config.SCREENSHOTS_DIR / datetime.now().strftime("frame_%Y%m%d_%H%M%S.png")
        vision.write_image(path, vision.grab(self.client))
        self.log(f"Saved screenshots/{path.name}")

    def exit_app(self):
        self.recorder.stop()
        self.runner.stop()
        inputs.release_all()
        self.hotkeys.stop()
        if self.editor:
            self.flow.save()
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
            kind = event[0]
            if kind == "log":
                self._append_log(event[1])
            elif kind == "f6":
                self.on_f6()
            elif kind == "f7":
                self.on_f7()
            elif kind == "step":
                self._on_step(event[1])
            elif kind == "ask_delay":
                self._ask_delay()

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
        # Border and always-on-top panel only while the game (or the panel) is in
        # front, so they never float over other apps or over the editor.
        active = win32.foreground_window() in (self.hwnd, win32.root_window(self.root.winfo_id()))
        if active:
            self.overlay.show(client, color)
        else:
            self.overlay.hide()
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
        text, color = "Mouse  —\nRGB    —", FIELD
        if self.client:
            sx, sy = win32.cursor_pos()
            x, y = sx - self.client.left, sy - self.client.top
            if 0 <= x < self.client.width and 0 <= y < self.client.height:
                b, g, r = (int(v) for v in vision.grab(win32.Rect(sx, sy, 1, 1))[0, 0])
                text = f"Mouse  {x}, {y}\nRGB    {r}, {g}, {b}"
                color = f"#{r:02x}{g:02x}{b:02x}"
            else:
                text = "Mouse  outside\nRGB    —"
        if text != self._mouse_text:
            self.mouse_label.configure(text=text)
            self.swatch.configure(bg=color)
            self._mouse_text = text

    def run(self):
        self.root.mainloop()
