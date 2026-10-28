"""Macros built from nodes, checkers and overseers, stored as JSON plus images.

On disk a macro is flows/<name>/flow.json with its pictures in
flows/<name>/images/. Pieces point at each other with strings such as
"node:farm" or "checker:after_wave"; None means "stop".

  node      a list of steps (keys, delays, clicks, image clicks/waits), then a next target
  checker   looks for several images; the first one seen picks the next target
  overseer  watched the whole time; when its image appears it interrupts,
            runs one node, then continues at a chosen target
"""
import json
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from . import config

FORMAT = 1
KINDS = ("node", "checker", "overseer")


def make_ref(kind, name):
    return f"{kind}:{name}"


def parse_ref(ref):
    kind, _, name = ref.partition(":")
    return kind, name


def ref_label(ref):
    """How a target is shown in dropdowns: "node: farm", or "(stop)"."""
    return ref.replace(":", ": ", 1) if ref else "(stop)"


def label_ref(label):
    return None if not label or label == "(stop)" else label.replace(": ", ":", 1)


def safe_name(text):
    return re.sub(r"[^\w\-]+", "_", (text or "").strip()).strip("_")


def unique_path(folder, stem, suffix=""):
    path, i = folder / f"{stem}{suffix}", 2
    while path.exists():
        path, i = folder / f"{stem}_{i}{suffix}", i + 1
    return path


def new_item(kind):
    if kind == "node":
        return {"steps": [], "next": None}
    if kind == "checker":
        return {"branches": [], "timeout": 30, "fallback": None}
    return {"image": None, "confidence": config.DEFAULT_CONFIDENCE, "run": None, "then": None}


def node_images(node):
    return {s["image"] for s in node["steps"] if s.get("image")}


def _pct(confidence):
    return f"{round((confidence or config.DEFAULT_CONFIDENCE) * 100)}%"


def describe_step(step):
    kind = step["type"]
    if kind == "key":
        key = step["key"]
        return f"Press {key.upper() if len(key) == 1 else key} for {step.get('hold', 0.05):g}s"
    if kind == "delay":
        return f"Wait {step['seconds']:g}s"
    if kind == "click":
        return f"{step.get('button', 'left').title()} click at ({step['x']}, {step['y']})"
    if kind in ("click_image", "wait_image"):
        verb = "Click" if kind == "click_image" else "Wait for"
        return (f'{verb} image "{step["image"]}" (match {_pct(step.get("confidence"))}, '
                f'up to {step.get("timeout", 10):g}s)')
    return f"Unknown step {kind!r}"


def _image_member(member):
    """Image name for a safe "images/<name>.png" zip entry, else None."""
    path = PurePosixPath(member)
    if (len(path.parts) == 2 and path.parts[0] == "images" and path.suffix.lower() == ".png"
            and safe_name(path.stem) == path.stem):
        return path.stem
    return None


class Flow:
    def __init__(self, folder, data):
        self.folder = Path(folder)
        self.data = data
        for key in ("nodes", "checkers", "overseers"):
            data.setdefault(key, {})
        data.setdefault("start", None)

    @classmethod
    def create(cls, name):
        folder = unique_path(config.FLOWS_DIR, safe_name(name) or "macro")
        flow = cls(folder, {"format": FORMAT, "kind": "flow",
                            "frame": [config.FRAME_WIDTH, config.FRAME_HEIGHT]})
        flow.save()
        return flow

    @classmethod
    def load(cls, folder):
        folder = Path(folder)
        return cls(folder, json.loads((folder / "flow.json").read_text(encoding="utf-8")))

    @property
    def name(self):
        return self.folder.name

    @property
    def images_dir(self):
        return self.folder / "images"

    @property
    def nodes(self):
        return self.data["nodes"]

    @property
    def checkers(self):
        return self.data["checkers"]

    @property
    def overseers(self):
        return self.data["overseers"]

    def items(self, kind):
        return self.data[kind + "s"]

    def save(self):
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.data["name"] = self.name
        (self.folder / "flow.json").write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def targets(self):
        """Every place the macro can go next."""
        return ([make_ref("node", n) for n in self.nodes]
                + [make_ref("checker", n) for n in self.checkers])

    def images(self):
        return sorted(p.stem for p in self.images_dir.glob("*.png"))

    def used_images(self):
        used = set()
        for node in self.nodes.values():
            used |= node_images(node)
        for checker in self.checkers.values():
            used |= {b["image"] for b in checker["branches"] if b.get("image")}
        used |= {o["image"] for o in self.overseers.values() if o.get("image")}
        return used

    # ------------------------------------------------------------- editing

    def unique_name(self, kind, base):
        base = safe_name(base) or kind
        name, i = base, 2
        while name in self.items(kind):
            name, i = f"{base}_{i}", i + 1
        return name

    def add(self, kind, base=None, item=None):
        name = self.unique_name(kind, base or kind)
        self.items(kind)[name] = item or new_item(kind)
        if kind != "overseer" and not self.data["start"]:
            self.data["start"] = make_ref(kind, name)
        self.save()
        return name

    def rename(self, kind, old, new):
        new = safe_name(new)
        if not new or new == old:
            return old
        if new in self.items(kind):
            raise ValueError(f'There is already a {kind} called "{new}"')
        self.data[kind + "s"] = {(new if k == old else k): v for k, v in self.items(kind).items()}
        if kind != "overseer":
            self._retarget(make_ref(kind, old), make_ref(kind, new))
        self.save()
        return new

    def delete(self, kind, name):
        self.items(kind).pop(name, None)
        if kind != "overseer":
            self._retarget(make_ref(kind, name), None)
        self.save()

    def _retarget(self, old, new):
        """Point every reference to `old` at `new` (None clears it)."""
        if self.data["start"] == old:
            self.data["start"] = new
        for node in self.nodes.values():
            if node.get("next") == old:
                node["next"] = new
        for checker in self.checkers.values():
            if checker.get("fallback") == old:
                checker["fallback"] = new
            for branch in checker["branches"]:
                if branch.get("goto") == old:
                    branch["goto"] = new
        for overseer in self.overseers.values():
            if overseer.get("then") == old:
                overseer["then"] = new
            if old.startswith("node:") and overseer.get("run") == parse_ref(old)[1]:
                overseer["run"] = parse_ref(new)[1] if new else None

    # ---------------------------------------------------------- validation

    def _exists(self, ref):
        kind, name = parse_ref(ref)
        return kind in ("node", "checker") and name in self.items(kind)

    def problems(self):
        """Things that would make the macro fail, as readable sentences."""
        out = []
        if not self.data["start"]:
            out.append("No start set (pick one in the editor's 'Start at').")
        refs = [("Start", self.data["start"])]
        refs += [(f'Node "{n}" next', v.get("next")) for n, v in self.nodes.items()]
        for name, checker in self.checkers.items():
            refs += [(f'Checker "{name}" branch', b.get("goto")) for b in checker["branches"]]
            refs.append((f'Checker "{name}" fallback', checker.get("fallback")))
            if not checker["branches"]:
                out.append(f'Checker "{name}" has nothing to look for.')
            if any(not b.get("image") for b in checker["branches"]):
                out.append(f'Checker "{name}" has a branch with no image.')
        for name, overseer in self.overseers.items():
            refs.append((f'Overseer "{name}" then', overseer.get("then")))
            if not overseer.get("image"):
                out.append(f'Overseer "{name}" has no image to watch for.')
            if overseer.get("run") and overseer["run"] not in self.nodes:
                out.append(f'Overseer "{name}" runs missing node "{overseer["run"]}".')
        out += [f"{where} points to missing {ref_label(ref)}." for where, ref in refs
                if ref and not self._exists(ref)]
        have = set(self.images())
        out += [f'Image "{image}" is missing from {self.name}/images.'
                for image in sorted(self.used_images() - have)]
        return out

    def frame_warning(self):
        frame = self.data.get("frame")
        if frame and tuple(frame) != (config.FRAME_WIDTH, config.FRAME_HEIGHT):
            return (f"{self.name} was made for a {frame[0]}x{frame[1]} frame but this app uses "
                    f"{config.FRAME_WIDTH}x{config.FRAME_HEIGHT}; clicks and images may be off.")
        return None

    # ----------------------------------------------------------- packaging

    def _write_images(self, archive, images):
        for image in sorted(images):
            source = self.images_dir / f"{image}.png"
            if source.exists():
                archive.write(source, f"images/{image}.png")

    def export_zip(self):
        """exports/<name>.zip: flow.json, INSTRUCTIONS.md and every image it uses."""
        config.EXPORTS_DIR.mkdir(exist_ok=True)
        path = config.EXPORTS_DIR / f"{self.name}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("flow.json", json.dumps(self.data, indent=2))
            archive.writestr("INSTRUCTIONS.md", flow_instructions(self))
            self._write_images(archive, self.used_images())
        return path

    def save_node_to_library(self, name):
        """library/<node>.zip: one node with its images, reusable in any macro."""
        config.LIBRARY_DIR.mkdir(exist_ok=True)
        node = {"steps": self.nodes[name]["steps"], "next": None}
        path = config.LIBRARY_DIR / f"{name}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("node.json", json.dumps({
                "format": FORMAT, "kind": "node", "name": name,
                "frame": [config.FRAME_WIDTH, config.FRAME_HEIGHT], "node": node}, indent=2))
            archive.writestr("INSTRUCTIONS.md", node_instructions(name, node))
            self._write_images(archive, node_images(node))
        return path

    def add_library_node(self, path):
        """Copy a library node (and its images) into this macro. Returns the new node's name."""
        with zipfile.ZipFile(path) as archive:
            data = json.loads(archive.read("node.json"))
            node = {"steps": [dict(s) for s in data["node"]["steps"]], "next": None}
            renamed = {}
            self.images_dir.mkdir(parents=True, exist_ok=True)
            for member in archive.namelist():
                image = _image_member(member)
                if not image:
                    continue
                content = archive.read(member)
                target = self.images_dir / f"{image}.png"
                if target.exists() and target.read_bytes() != content:
                    target = unique_path(self.images_dir, image, ".png")
                    renamed[image] = target.stem
                target.write_bytes(content)
        for step in node["steps"]:
            if step.get("image") in renamed:
                step["image"] = renamed[step["image"]]
        return self.add("node", data.get("name") or Path(path).stem, node)


def list_flows():
    return sorted(p.parent for p in config.FLOWS_DIR.glob("*/flow.json"))


def list_library():
    return sorted(config.LIBRARY_DIR.glob("*.zip"))


def import_zip(path):
    """Add a shared zip: a whole macro goes to flows/, a single node to library/.

    Returns (kind, name). Only flow.json/node.json and images/*.png are taken
    from the zip, so a zip can't write anywhere else.
    """
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        members = set(archive.namelist())
        if "flow.json" in members:
            data = json.loads(archive.read("flow.json"))
            if data.get("kind") != "flow":
                raise ValueError(f"{path.name} does not contain an AA Macro macro")
            folder = unique_path(config.FLOWS_DIR, safe_name(data.get("name")) or safe_name(path.stem) or "macro")
            (folder / "images").mkdir(parents=True)
            for member in members:
                image = _image_member(member)
                if image:
                    (folder / "images" / f"{image}.png").write_bytes(archive.read(member))
            flow = Flow(folder, data)
            flow.save()
            return "flow", flow.name
        if "node.json" in members:
            if json.loads(archive.read("node.json")).get("kind") != "node":
                raise ValueError(f"{path.name} does not contain an AA Macro node")
            config.LIBRARY_DIR.mkdir(exist_ok=True)
            target = unique_path(config.LIBRARY_DIR, safe_name(path.stem) or "node", ".zip")
            shutil.copyfile(path, target)
            return "node", target.stem
    raise ValueError(f"{path.name} has no flow.json or node.json, so it isn't an AA Macro zip")


# ---------------------------------------------------------------- instructions

def _steps_text(node):
    if not node["steps"]:
        return "(no steps yet)\n"
    return "".join(f"{i}. {describe_step(s)}\n" for i, s in enumerate(node["steps"], 1))


def node_instructions(name, node):
    return (f"# Node: {name}\n\n"
            f"Frame: {config.FRAME_WIDTH} x {config.FRAME_HEIGHT}. Clicks are pixels inside the Roblox game area.\n"
            "Import this zip in AA Macro (Input mode > Import zip), then in the editor use\n"
            "Nodes > + Library to add it to a macro.\n\n"
            "## Steps\n\n" + _steps_text(node))


def flow_instructions(flow):
    lines = [f"# Macro: {flow.name}", "",
             f"Frame: {config.FRAME_WIDTH} x {config.FRAME_HEIGHT}. Clicks are pixels inside the Roblox game area.",
             "Import this zip in AA Macro (Input mode > Import zip), then run it from Macro mode.", "",
             f"Starts at: {ref_label(flow.data['start'])}", ""]
    if flow.nodes:
        lines += ["## Nodes", ""]
        for name, node in flow.nodes.items():
            lines += [f"### {name}", "", _steps_text(node).rstrip(), "",
                      f"Then: {ref_label(node.get('next'))}", ""]
    if flow.checkers:
        lines += ["## Checkers", ""]
        for name, checker in flow.checkers.items():
            lines += [f"### {name}", "", f"Look for up to {checker.get('timeout', 30):g}s:"]
            lines += [f'- "{b.get("image")}" (match {_pct(b.get("confidence"))}) -> {ref_label(b.get("goto"))}'
                      for b in checker["branches"]]
            lines += [f"- nothing seen -> {ref_label(checker.get('fallback'))}", ""]
    if flow.overseers:
        lines += ["## Overseers", ""]
        for name, overseer in flow.overseers.items():
            lines += [f"### {name}", "",
                      f'Whenever "{overseer.get("image")}" (match {_pct(overseer.get("confidence"))}) appears: '
                      f'stop the current node, run node "{overseer.get("run") or "(none)"}", '
                      f'then go to {ref_label(overseer.get("then"))}.', ""]
    return "\n".join(lines) + "\n"
