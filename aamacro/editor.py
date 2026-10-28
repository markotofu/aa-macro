"""Create mode's editor: build a macro's nodes, checkers and overseers and connect them."""
import tkinter as tk
from tkinter import messagebox, ttk

from . import config, inputs
from .flow import (describe_step, label_ref, list_library, make_ref, parse_ref, ref_label)
from .theme import BG, MUTED, listbox
from .tools import ask_form

TITLES = {
    "node": ("Nodes", "do steps"),
    "checker": ("Checkers", "choose what runs next"),
    "overseer": ("Overseers", "interrupt when seen"),
}
NEW_IMAGE = "(capture new…)"
RECORD_HINT = ("Recording: in Roblox press  \\  then a key to record it,  ]  to add a delay,  "
               "[  to click where the cursor is. F6 stops.")


class Editor:
    def __init__(self, app, flow):
        self.app = app
        self.flow = flow
        self.selected = None  # (kind, name)
        win = self.win = tk.Toplevel(app.root)
        win.title(f"AA Macro editor: {flow.name}")
        win.configure(bg=BG)
        win.geometry("900x640")
        win.minsize(820, 560)
        win.protocol("WM_DELETE_WINDOW", self.close)

        top = ttk.Frame(win, padding=(12, 10, 12, 0))
        top.pack(fill="x")
        ttk.Label(top, text=flow.name, style="Head.TLabel").pack(side="left")
        ttk.Button(top, text="Export zip", command=self.export).pack(side="right")
        ttk.Button(top, text="Run macro", style="Accent.TButton",
                   command=lambda: app.run_flow(flow)).pack(side="right", padx=6)
        self.start_box = self._target_box(top, lambda: flow.data["start"], self._set_start, allow_stop=False)
        self.start_box.pack(side="right")
        ttk.Label(top, text="Start at").pack(side="right", padx=(0, 6))

        main = ttk.Frame(win, padding=12)
        main.pack(fill="both", expand=True)
        left = ttk.Frame(main)
        left.pack(side="left", fill="y")
        self.detail = ttk.Frame(main, padding=(16, 0, 0, 0))
        self.detail.pack(side="left", fill="both", expand=True)

        self.lists = {}
        for kind in ("node", "checker", "overseer"):
            title, blurb = TITLES[kind]
            head = ttk.Frame(left)
            head.pack(fill="x", pady=(6, 2))
            ttk.Label(head, text=title.upper(), style="Section.TLabel").pack(side="left")
            ttk.Label(head, text=blurb, style="Muted.TLabel").pack(side="left", padx=6)
            lb = listbox(left, height=7, width=32)
            lb.pack(fill="x")
            lb.bind("<<ListboxSelect>>", lambda e, k=kind: self._on_list_select(k))
            self.lists[kind] = lb
            row = ttk.Frame(left)
            row.pack(fill="x", pady=(3, 0))
            buttons = [("+ New", lambda k=kind: self.new_item(k))]
            if kind == "node":
                buttons.append(("+ From library", self.add_from_library))
            buttons.append(("Delete", lambda k=kind: self.delete_item(k)))
            for text, command in buttons:
                ttk.Button(row, text=text, command=command).pack(side="left", fill="x", expand=True, padx=1)

        self.refresh_lists()
        first = next(iter(flow.nodes), None)
        if first:
            self.select("node", first)
        else:
            self._empty_detail()

    # ------------------------------------------------------------ helpers

    def _save(self):
        self.flow.save()

    def _set_start(self, ref):
        self.flow.data["start"] = ref
        self._save()

    def _target_box(self, parent, get_value, on_change, allow_stop=True, nodes_only=False, width=26):
        """Dropdown of places the macro can go next."""
        var = tk.StringVar(value=ref_label(get_value()))

        def values():
            refs = [r for r in self.flow.targets() if not nodes_only or r.startswith("node:")]
            return (["(stop)"] if allow_stop else []) + [ref_label(r) for r in refs]

        box = ttk.Combobox(parent, textvariable=var, state="readonly", width=width, values=values())
        box.configure(postcommand=lambda: box.configure(values=values()))
        box.bind("<<ComboboxSelected>>", lambda e: on_change(label_ref(var.get())))
        return box

    def _image_choice(self, value=None):
        return {"key": "image", "label": "Image", "kind": "choice",
                "options": [NEW_IMAGE] + self.flow.images(), "value": value or NEW_IMAGE}

    def _with_image(self, answer, apply, suggested=""):
        """Run apply(image_name) now, or after capturing a new image if that was chosen."""
        if answer["image"] == NEW_IMAGE:
            self.app.capture(self.flow.images_dir, lambda name, region: apply(name), suggested)
        else:
            apply(answer["image"])

    def _clear_detail(self):
        for child in self.detail.winfo_children():
            child.destroy()

    def _empty_detail(self):
        self._clear_detail()
        ttk.Label(self.detail, style="Muted.TLabel", justify="left", wraplength=480, text=(
            "Add a node with + New, select it, and press Record (F6) to record steps in Roblox.\n\n"
            "Nodes do things. Point a node's 'Then go to' at a checker to branch on what's on "
            "screen, and add overseers for things that can pop up at any time.")).pack(anchor="w")

    def _header(self, kind, name, test_text="Test"):
        row = ttk.Frame(self.detail)
        row.pack(fill="x")
        ttk.Label(row, text=f"{kind.title()}", style="Section.TLabel").pack(side="left", padx=(0, 8))
        var = tk.StringVar(value=name)
        entry = ttk.Entry(row, textvariable=var, width=26)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: self._rename(kind, name, var.get()))
        entry.bind("<FocusOut>", lambda e: self._rename(kind, name, var.get()))
        ttk.Button(row, text=test_text, command=lambda: self.app.test_piece(self.flow, kind, name)) \
            .pack(side="right")

    def _rename(self, kind, old, new):
        if (kind, old) != self.selected or new == old:
            return
        try:
            new = self.flow.rename(kind, old, new)
        except ValueError as exc:
            messagebox.showerror("Rename", str(exc), parent=self.win)
            return
        if new != old:
            if kind == "node":
                self.app.on_node_renamed(self.flow, old, new)
            self.refresh_lists()
            self.select(kind, new)

    # -------------------------------------------------------------- lists

    def refresh_lists(self):
        for kind, lb in self.lists.items():
            lb.delete(0, "end")
            for name in self.flow.items(kind):
                lb.insert("end", name)
        self.start_box.set(ref_label(self.flow.data["start"]))
        if self.selected:
            kind, name = self.selected
            names = list(self.flow.items(kind))
            if name in names:
                self.lists[kind].selection_set(names.index(name))

    def _on_list_select(self, kind):
        selection = self.lists[kind].curselection()
        if selection:
            self.select(kind, self.lists[kind].get(selection[0]))

    def select(self, kind, name):
        self.selected = (kind, name)
        for other, lb in self.lists.items():
            lb.selection_clear(0, "end")
            if other == kind:
                names = list(self.flow.items(kind))
                if name in names:
                    lb.selection_set(names.index(name))
        self._clear_detail()
        {"node": self._node_detail, "checker": self._checker_detail,
         "overseer": self._overseer_detail}[kind](name)

    def selected_node(self):
        return self.selected[1] if self.selected and self.selected[0] == "node" else None

    def new_item(self, kind):
        answer = ask_form(self.win, f"New {kind}", [
            {"key": "name", "label": "Name", "value": self.flow.unique_name(kind, kind)}])
        if answer:
            name = self.flow.add(kind, answer["name"])
            self.refresh_lists()
            self.select(kind, name)

    def delete_item(self, kind):
        selection = self.lists[kind].curselection()
        if not selection:
            return
        name = self.lists[kind].get(selection[0])
        if not messagebox.askyesno("Delete", f'Delete {kind} "{name}"? Anything pointing to it will stop there.',
                                   parent=self.win):
            return
        if kind == "node":
            self.app.on_node_deleted(self.flow, name)
        self.flow.delete(kind, name)
        self.selected = None
        self.refresh_lists()
        self._empty_detail()

    def add_from_library(self):
        zips = list_library()
        if not zips:
            messagebox.showinfo("Library", "The library is empty. Nodes are added to it when you stop "
                                "recording them or press 'Save to library'.", parent=self.win)
            return
        answer = ask_form(self.win, "Add node from library", [
            {"key": "node", "label": "Node", "kind": "choice", "options": [p.stem for p in zips],
             "value": zips[0].stem}])
        if answer:
            path = next(p for p in zips if p.stem == answer["node"])
            name = self.flow.add_library_node(path)
            self.app.log(f'Added library node "{answer["node"]}" as "{name}"')
            self.refresh_lists()
            self.select("node", name)

    def export(self):
        path = self.flow.export_zip()
        self.app.log(f"Exported {path.parent.name}/{path.name}")

    def close(self):
        if self.app.recording:
            self.app.stop_recording()
        self.export()
        self.app.editor = None
        self.win.destroy()

    # --------------------------------------------------------------- node

    def _node_detail(self, name):
        node = self.flow.nodes[name]
        self._header("node", name, "Test node")
        body = ttk.Frame(self.detail)
        body.pack(fill="both", expand=True, pady=8)
        self.steps_list = listbox(body, height=16, width=52)
        self.steps_list.pack(side="left", fill="both", expand=True)
        self.steps_list.bind("<Double-Button-1>", lambda e: self.edit_step())
        scroll = ttk.Scrollbar(body, command=self.steps_list.yview)
        self.steps_list.configure(yscrollcommand=scroll.set)
        scroll.pack(side="left", fill="y")
        tools = ttk.Frame(body, padding=(8, 0, 0, 0))
        tools.pack(side="left", fill="y")
        self.record_button = ttk.Button(tools, style="Accent.TButton",
                                        command=lambda: self.app.toggle_recording(self.flow, name))
        self.record_button.pack(fill="x", pady=(0, 6))
        for item in [
                ("+ Key…", self.add_key), ("+ Delay…", self.add_delay), ("+ Click…", self.add_click),
                ("+ Click image…", lambda: self.add_image_step("click_image")),
                ("+ Wait for image…", lambda: self.add_image_step("wait_image")), None,
                ("Edit…", self.edit_step), ("Move up", lambda: self.move_step(-1)),
                ("Move down", lambda: self.move_step(1)), ("Delete step", self.delete_step)]:
            if item is None:
                ttk.Separator(tools).pack(fill="x", pady=6)
            else:
                ttk.Button(tools, text=item[0], command=item[1]).pack(fill="x", pady=1)

        row = ttk.Frame(self.detail)
        row.pack(fill="x")
        ttk.Label(row, text="Then go to").pack(side="left", padx=(0, 6))
        self._target_box(row, lambda: node.get("next"), lambda ref: self._set(node, "next", ref)).pack(side="left")
        ttk.Button(row, text="Save to library", command=lambda: self.app.save_node_to_library(self.flow, name)) \
            .pack(side="right")
        self.record_hint = ttk.Label(self.detail, style="Muted.TLabel", wraplength=560, justify="left")
        self.record_hint.pack(anchor="w", pady=(8, 0))
        self.refresh_steps()
        self.update_record_state()

    def _set(self, item, key, value):
        item[key] = value
        self._save()

    def _steps(self):
        return self.flow.nodes[self.selected[1]]["steps"]

    def refresh_steps(self, select=None):
        if not self.selected_node() or not self.steps_list.winfo_exists():
            return
        lb = self.steps_list
        lb.delete(0, "end")
        for i, step in enumerate(self._steps(), 1):
            lb.insert("end", f"{i:>2}. {describe_step(step)}")
        if select is not None and lb.size():
            select = min(select, lb.size() - 1)
            lb.selection_set(select)
            lb.see(select)

    def on_step_recorded(self, node):
        if self.selected_node() == node:
            self.refresh_steps(select=len(self._steps()) - 1)

    def update_record_state(self):
        if not self.selected_node() or not self.record_button.winfo_exists():
            return
        recording = self.app.recording == (self.flow, self.selected_node())
        self.record_button.configure(text="■ Stop recording (F6)" if recording else "● Record (F6)")
        self.record_hint.configure(text=RECORD_HINT if recording else
                                   "Record (F6) adds steps from Roblox at the end of this list. "
                                   "Steps run top to bottom, then 'Then go to' runs.")

    def _selected_step(self):
        selection = self.steps_list.curselection()
        return selection[0] if selection else None

    def _insert_step(self, step):
        steps = self._steps()
        index = self._selected_step()
        index = len(steps) if index is None else index + 1
        steps.insert(index, step)
        self._save()
        self.refresh_steps(select=index)

    def _key_fields(self, key="", hold=0.05):
        return [{"key": "key", "label": "Key", "value": key, "help": "e.g. w, space, e, f1, shift"},
                {"key": "hold", "label": "Hold (seconds)", "kind": "float", "value": hold}]

    def _valid_key(self, key):
        try:
            inputs.vk_for(key)
            return True
        except ValueError:
            messagebox.showerror("Key", f'"{key}" isn\'t a key name I know.', parent=self.win)
            return False

    def add_key(self):
        answer = ask_form(self.win, "Add key press", self._key_fields())
        if answer and self._valid_key(answer["key"]):
            self._insert_step({"type": "key", "key": answer["key"].lower() if len(answer["key"]) > 1
                               else answer["key"], "hold": answer["hold"]})

    def add_delay(self):
        answer = ask_form(self.win, "Add delay", [
            {"key": "seconds", "label": "Seconds to wait", "kind": "float", "value": 1.0}])
        if answer:
            self._insert_step({"type": "delay", "seconds": answer["seconds"]})

    def add_click(self):
        self.app.pick_point(lambda x, y: self._insert_step({"type": "click", "x": x, "y": y, "button": "left"}))

    def _image_step_fields(self, kind, step=None):
        step = step or {}
        fields = [self._image_choice(step.get("image")),
                  {"key": "confidence", "label": "Match at least (%)", "kind": "percent",
                   "value": step.get("confidence", config.DEFAULT_CONFIDENCE),
                   "help": "lower = more forgiving"},
                  {"key": "timeout", "label": "Wait up to (seconds)", "kind": "float",
                   "value": step.get("timeout", 10)}]
        if kind == "click_image":
            fields.append({"key": "button", "label": "Button", "kind": "choice",
                           "options": ["left", "right"], "value": step.get("button", "left")})
        return fields

    def add_image_step(self, kind):
        title = "Click an image" if kind == "click_image" else "Wait for an image"
        answer = ask_form(self.win, title, self._image_step_fields(kind))
        if not answer:
            return

        def apply(image):
            step = {"type": kind, "image": image, "confidence": answer["confidence"], "timeout": answer["timeout"]}
            if kind == "click_image":
                step["button"] = answer["button"]
            self._insert_step(step)
        self._with_image(answer, apply)

    def edit_step(self):
        index = self._selected_step()
        if index is None:
            return
        step = self._steps()[index]
        kind = step["type"]
        if kind == "key":
            answer = ask_form(self.win, "Edit key press", self._key_fields(step["key"], step.get("hold", 0.05)))
            if answer and self._valid_key(answer["key"]):
                step.update(answer)
        elif kind == "delay":
            answer = ask_form(self.win, "Edit delay", [
                {"key": "seconds", "label": "Seconds to wait", "kind": "float", "value": step["seconds"]}])
            if answer:
                step.update(answer)
        elif kind == "click":
            answer = ask_form(self.win, "Edit click", [
                {"key": "x", "label": f"X (0-{config.FRAME_WIDTH - 1})", "kind": "int", "value": step["x"]},
                {"key": "y", "label": f"Y (0-{config.FRAME_HEIGHT - 1})", "kind": "int", "value": step["y"]},
                {"key": "button", "label": "Button", "kind": "choice", "options": ["left", "right", "middle"],
                 "value": step.get("button", "left")}])
            if answer:
                answer["x"] = min(answer["x"], config.FRAME_WIDTH - 1)
                answer["y"] = min(answer["y"], config.FRAME_HEIGHT - 1)
                step.update(answer)
        else:
            answer = ask_form(self.win, "Edit image step", self._image_step_fields(kind, step))
            if answer:
                def apply(image):
                    step.update(answer, image=image)
                    self._save()
                    self.refresh_steps(select=index)
                self._with_image(answer, apply)
                return
        self._save()
        self.refresh_steps(select=index)

    def move_step(self, delta):
        index = self._selected_step()
        steps = self._steps()
        if index is None or not 0 <= index + delta < len(steps):
            return
        steps[index], steps[index + delta] = steps[index + delta], steps[index]
        self._save()
        self.refresh_steps(select=index + delta)

    def delete_step(self):
        index = self._selected_step()
        if index is not None:
            del self._steps()[index]
            self._save()
            self.refresh_steps(select=index)

    # ------------------------------------------------------------ checker

    def _checker_detail(self, name):
        checker = self.flow.checkers[name]
        self._header("checker", name, "Test checker")
        ttk.Label(self.detail, style="Muted.TLabel", wraplength=560, justify="left", text=(
            "Looks at the screen for these images. The first one seen decides what runs next. "
            "Point a node's 'Then go to' here to use it.")).pack(anchor="w", pady=(8, 4))
        self.branch_list = listbox(self.detail, height=9)
        self.branch_list.pack(fill="x")
        self.branch_list.bind("<Double-Button-1>", lambda e: self.edit_branch(checker))
        row = ttk.Frame(self.detail)
        row.pack(fill="x", pady=(4, 10))
        for text, command in [("+ Branch…", lambda: self.edit_branch(checker, new=True)),
                              ("Edit…", lambda: self.edit_branch(checker)),
                              ("Move up", lambda: self.move_branch(checker, -1)),
                              ("Move down", lambda: self.move_branch(checker, 1)),
                              ("Delete", lambda: self.delete_branch(checker))]:
            ttk.Button(row, text=text, command=command).pack(side="left", padx=(0, 2))

        row = ttk.Frame(self.detail)
        row.pack(fill="x")
        ttk.Label(row, text="If nothing is seen within").pack(side="left")
        timeout = tk.StringVar(value=f"{checker.get('timeout', 30):g}")
        entry = ttk.Entry(row, textvariable=timeout, width=6)
        entry.pack(side="left", padx=4)

        def save_timeout(_=None):
            try:
                checker["timeout"] = max(0.0, float(timeout.get()))
                self._save()
            except ValueError:
                timeout.set(f"{checker.get('timeout', 30):g}")
        entry.bind("<Return>", save_timeout)
        entry.bind("<FocusOut>", save_timeout)
        ttk.Label(row, text="seconds, go to").pack(side="left", padx=(0, 6))
        self._target_box(row, lambda: checker.get("fallback"),
                         lambda ref: self._set(checker, "fallback", ref)).pack(side="left")
        self.refresh_branches(checker)

    def refresh_branches(self, checker, select=None):
        lb = self.branch_list
        lb.delete(0, "end")
        for branch in checker["branches"]:
            lb.insert("end", f'If "{branch.get("image")}" (match {round(branch.get("confidence", 0.8) * 100)}%)'
                             f'  →  {ref_label(branch.get("goto"))}')
        if select is not None and lb.size():
            lb.selection_set(min(select, lb.size() - 1))

    def edit_branch(self, checker, new=False):
        selection = self.branch_list.curselection()
        if not new and not selection:
            return
        branch = {} if new else checker["branches"][selection[0]]
        targets = ["(stop)"] + [ref_label(r) for r in self.flow.targets()]
        answer = ask_form(self.win, "Branch", [
            self._image_choice(branch.get("image")),
            {"key": "confidence", "label": "Match at least (%)", "kind": "percent",
             "value": branch.get("confidence", config.DEFAULT_CONFIDENCE), "help": "lower = more forgiving"},
            {"key": "goto", "label": "When seen, go to", "kind": "choice", "options": targets,
             "value": ref_label(branch.get("goto"))}])
        if not answer:
            return

        def apply(image):
            branch.update(image=image, confidence=answer["confidence"], goto=label_ref(answer["goto"]))
            if new:
                checker["branches"].append(branch)
            self._save()
            if self.selected and self.selected[0] == "checker":
                self.refresh_branches(checker, select=checker["branches"].index(branch))
        self._with_image(answer, apply)

    def move_branch(self, checker, delta):
        selection = self.branch_list.curselection()
        branches = checker["branches"]
        if not selection or not 0 <= selection[0] + delta < len(branches):
            return
        i = selection[0]
        branches[i], branches[i + delta] = branches[i + delta], branches[i]
        self._save()
        self.refresh_branches(checker, select=i + delta)

    def delete_branch(self, checker):
        selection = self.branch_list.curselection()
        if selection:
            del checker["branches"][selection[0]]
            self._save()
            self.refresh_branches(checker, select=selection[0])

    # ----------------------------------------------------------- overseer

    def _overseer_detail(self, name):
        overseer = self.flow.overseers[name]
        self._header("overseer", name, "Check now")
        ttk.Label(self.detail, style="Muted.TLabel", wraplength=560, justify="left", text=(
            "Watched the whole time the macro runs. When the image appears, the current node stops, "
            "the node below runs, then the macro goes where you choose. It won't fire again until "
            "the image has gone away.")).pack(anchor="w", pady=(8, 10))
        grid = ttk.Frame(self.detail)
        grid.pack(fill="x")

        ttk.Label(grid, text="Watch for image").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
        image = tk.StringVar(value=overseer.get("image") or "")
        image_box = ttk.Combobox(grid, textvariable=image, state="readonly", width=26,
                                 values=[NEW_IMAGE] + self.flow.images())
        image_box.grid(row=0, column=1, sticky="w")

        def pick_image(_=None):
            if image.get() == NEW_IMAGE:
                image.set(overseer.get("image") or "")
                self.app.capture(self.flow.images_dir, lambda n, r: (self._set(overseer, "image", n),
                                                                     self.select("overseer", name)), name)
            else:
                self._set(overseer, "image", image.get())
        image_box.bind("<<ComboboxSelected>>", pick_image)

        ttk.Label(grid, text="Match at least (%)").grid(row=1, column=0, sticky="w", pady=4)
        confidence = tk.StringVar(value=str(round(overseer.get("confidence", 0.8) * 100)))
        entry = ttk.Entry(grid, textvariable=confidence, width=6)
        entry.grid(row=1, column=1, sticky="w")

        def save_confidence(_=None):
            try:
                overseer["confidence"] = min(max(float(confidence.get()) / 100, 0.3), 1.0)
                self._save()
            except ValueError:
                pass
            confidence.set(str(round(overseer["confidence"] * 100)))
        entry.bind("<Return>", save_confidence)
        entry.bind("<FocusOut>", save_confidence)

        ttk.Label(grid, text="Then run node").grid(row=2, column=0, sticky="w", pady=4)
        self._target_box(grid, lambda: make_ref("node", overseer["run"]) if overseer.get("run") else None,
                         lambda ref: self._set(overseer, "run", parse_ref(ref)[1] if ref else None),
                         nodes_only=True).grid(row=2, column=1, sticky="w")

        ttk.Label(grid, text="After that, go to").grid(row=3, column=0, sticky="w", pady=4)
        self._target_box(grid, lambda: overseer.get("then"),
                         lambda ref: self._set(overseer, "then", ref)).grid(row=3, column=1, sticky="w")
        ttk.Label(self.detail, style="Muted.TLabel", foreground=MUTED, text=(
            "Run node '(stop)' means: just interrupt and jump to 'After that'.")).pack(anchor="w", pady=(10, 0))
