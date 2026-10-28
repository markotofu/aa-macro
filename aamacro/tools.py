"""Pop-up tools: grab an image or pick a point on a frozen copy of the game, and small forms."""
import base64
import re
import tkinter as tk
from tkinter import messagebox, ttk

import cv2

from . import vision
from .theme import BG, FG, OK


def _photo(img):
    ok, data = cv2.imencode(".png", img)
    return tk.PhotoImage(data=base64.b64encode(data.tobytes()).decode())


class FrozenFrame:
    """A borderless window placed exactly over the game area, showing a still screenshot."""

    def __init__(self, root, client, image, hint):
        self.image = image
        self.on_close = None
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(f"{client.width}x{client.height}+{client.left}+{client.top}")
        self.photo = _photo(image)
        c = self.canvas = tk.Canvas(self.win, width=client.width, height=client.height,
                                    highlightthickness=0, bd=0, cursor="crosshair")
        c.pack()
        c.create_image(0, 0, anchor="nw", image=self.photo)
        text = c.create_text(client.width // 2, 18, fill=FG, font=("Segoe UI", 11, "bold"),
                             text=f"{hint}   ·   Esc to cancel")
        x0, y0, x1, y1 = c.bbox(text)
        self.hint = (c.create_rectangle(x0 - 10, y0 - 5, x1 + 10, y1 + 5, fill=BG, outline=""), text)
        c.tag_raise(text)
        self.win.bind("<Escape>", lambda e: self.close())
        self.win.focus_force()

    def hide_hint(self):
        for item in self.hint:
            self.canvas.itemconfigure(item, state="hidden")

    def clamp(self, event):
        h, w = self.image.shape[:2]
        return min(max(event.x, 0), w - 1), min(max(event.y, 0), h - 1)

    def close(self):
        self.win.destroy()
        if self.on_close:
            self.on_close()


class CaptureTool(FrozenFrame):
    """Drag a box around something to save it as images_dir/<name>.png.

    on_saved(name, (x, y, w, h)) is called after saving.
    """

    def __init__(self, root, client, image, images_dir, on_saved, suggested=""):
        super().__init__(root, client, image, "Drag around what the macro should look for")
        self.images_dir = images_dir
        self.on_saved = on_saved
        self.suggested = suggested
        self.start = None
        self.box = self.canvas.create_rectangle(0, 0, 0, 0, outline=OK, width=2, state="hidden")
        self.label = self.canvas.create_text(0, 0, anchor="sw", fill=OK, font=("Consolas", 9),
                                             state="hidden")
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)

    def _press(self, event):
        self.start = self.clamp(event)
        self.hide_hint()
        self.canvas.itemconfigure(self.box, state="normal")
        self.canvas.itemconfigure(self.label, state="normal")
        self._drag(event)

    def _drag(self, event):
        if not self.start:
            return
        (x0, y0), (x1, y1) = self.start, self.clamp(event)
        self.canvas.coords(self.box, x0, y0, x1, y1)
        self.canvas.coords(self.label, min(x0, x1), min(y0, y1) - 3)
        self.canvas.itemconfigure(self.label, text=f"({min(x0, x1)}, {min(y0, y1)})  "
                                                   f"{abs(x1 - x0)}x{abs(y1 - y0)}")

    def _release(self, event):
        if not self.start:
            return
        (x0, y0), (x1, y1) = self.start, self.clamp(event)
        self.start = None
        x, y, w, h = min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)
        if w < 4 or h < 4:
            return
        while True:
            answer = ask_form(self.win, "Save image", [
                {"key": "name", "label": f"Name for this {w}x{h} image", "value": self.suggested}])
            if answer is None:
                return  # cancelled: let them drag again
            name = re.sub(r"[^\w\-]+", "_", answer["name"].strip()).strip("_")
            if not name:
                continue
            path = self.images_dir / f"{name}.png"
            if path.exists() and not messagebox.askyesno(
                    "Replace image", f'"{name}" already exists. Replace it?', parent=self.win):
                continue
            break
        vision.write_image(path, self.image[y:y + h, x:x + w])
        self.close()
        self.on_saved(name, (x, y, w, h))


class PointPicker(FrozenFrame):
    """Click a spot; on_pick(x, y) gets its frame coordinates."""

    def __init__(self, root, client, image, on_pick):
        super().__init__(root, client, image, "Click where the macro should click")
        self.on_pick = on_pick
        self.canvas.bind("<ButtonRelease-1>", self._click)

    def _click(self, event):
        x, y = self.clamp(event)
        self.close()
        self.on_pick(x, y)


class _Form:
    def __init__(self, parent, title, fields):
        self.fields = fields
        self.result = None
        self.vars = {}
        win = self.win = tk.Toplevel(parent)
        win.title(title)
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(parent)
        win.attributes("-topmost", True)
        body = ttk.Frame(win, padding=14)
        body.pack(fill="both", expand=True)
        first = None
        for row, field in enumerate(fields):
            ttk.Label(body, text=field["label"]).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
            kind = field.get("kind", "text")
            value = field.get("value", "")
            if kind == "percent":
                value = round((value or 0) * 100)
            var = tk.StringVar(value="" if value is None else str(value))
            if kind == "choice":
                widget = ttk.Combobox(body, textvariable=var, values=field["options"], width=30,
                                      state="normal" if field.get("editable") else "readonly")
            else:
                widget = ttk.Entry(body, textvariable=var, width=32)
            widget.grid(row=row, column=1, sticky="ew", pady=3)
            if field.get("help"):
                ttk.Label(body, text=field["help"], style="Muted.TLabel").grid(
                    row=row, column=2, sticky="w", padx=(6, 0))
            self.vars[field["key"]] = var
            first = first or widget
        buttons = ttk.Frame(body)
        buttons.grid(row=len(fields), column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(buttons, text="OK", style="Accent.TButton", command=self._ok).pack(side="right", padx=6)
        win.bind("<Return>", lambda e: self._ok())
        win.bind("<Escape>", lambda e: win.destroy())
        win.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - win.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - win.winfo_height()) // 3)
        win.geometry(f"+{x}+{y}")
        win.grab_set()
        win.focus_force()
        if first is not None:
            first.focus_set()
        win.wait_window()

    def _ok(self):
        result = {}
        for field in self.fields:
            raw = self.vars[field["key"]].get().strip()
            kind = field.get("kind", "text")
            try:
                if kind == "float":
                    value = float(raw)
                elif kind == "int":
                    value = int(raw)
                elif kind == "percent":
                    value = min(max(float(raw.rstrip("%")) / 100, 0.3), 1.0)
                else:
                    value = raw
            except ValueError:
                messagebox.showerror("Invalid value", f'"{field["label"]}" needs a number.', parent=self.win)
                return
            if kind in ("float", "int") and value < 0:
                messagebox.showerror("Invalid value", f'"{field["label"]}" can\'t be negative.', parent=self.win)
                return
            result[field["key"]] = value
        self.result = result
        self.win.destroy()


def ask_form(parent, title, fields):
    """Show a small modal form and return {key: value}, or None if cancelled.

    Each field is a dict: key, label, value, kind (text/float/int/percent/choice),
    options (for choice), editable (choice that also accepts typing), help.
    """
    return _Form(parent, title, fields).result
