# AA Macro

A Roblox macro tool for Windows that behaves the same on any screen size.

It finds the Roblox window and resizes its game area to a fixed **800 × 600** frame.
It draws a green border around the frame and docks a control panel beside it. Every
click and image search uses coordinates inside that frame. A macro made on a 4K
monitor therefore works on a 1366×768 laptop.

## Setup and run

Requires Windows and Python 3.10 or newer. Open Roblox in a window (not F11 fullscreen),
then double-click **`run.bat`**. The first run creates `.venv` and installs the
libraries (mss, numpy, opencv-python).

| Key | Action |
|---|---|
| F6 | Create mode: start/stop recording. Macro mode: run/stop the selected macro. |
| F7 | Stop whatever is running or recording |
| F8 | Exit the app immediately, from anywhere |

## The three modes

The buttons under **Snap to Roblox** switch modes.

- **Create** lets you build macros. Pick or make a macro, then click **Open editor**.
- **Macro** runs a macro from your list.
- **Input** adds macros to your list: import zips someone shared, or add `.py` macros.
  You can also export or remove macros here.

## How a macro is built

A macro is made of three kinds of pieces, which you connect in the editor:

| Piece | What it does |
|---|---|
| **Node** | A list of steps that run top to bottom: key presses, delays, clicks, "click this image", "wait for this image". When it ends, it goes to its **Then go to** target. |
| **Checker** | Looks at the screen for several images. The **first one seen** decides which node or checker runs next. If none appears within the timeout, it goes to its fallback. |
| **Overseer** | Watches the screen the **whole time** the macro runs. When its image appears, it stops the current node, runs its own node, then continues where you chose. It won't fire again until that image has gone away. |

Each **Test** button runs just that piece right away. **Run macro** runs the whole thing
from **Start at**. Every target can also be **(stop)**, which ends the macro.

Example: `start` (click Play) → checker `result` → `won` goes to node `next_stage` /
`lost` goes to node `retry` → back to `start`, plus an overseer `disconnected` that runs
node `reconnect` and then goes to `start`.

### Recording a node

1. In the editor, select a node and press **Record** (or F6).
2. Switch to Roblox and play normally. Use these keys to add steps:

| Key | Adds |
|---|---|
| `\` then a key | That key press. Hold the key to record how long it was held. |
| `]` | A delay. You're asked for the number of seconds. |
| `[` | A left click where the cursor is. It also clicks, so the game keeps up. |

3. Press F6 again to stop. The game never receives `\`, `[` or `]` while you're recording.

You can also add or edit steps by hand with the buttons beside the step list.
**+ Click…** and the image steps freeze the game so you can click a point or drag around
the picture to look for. When a macro plays, the mouse glides to each click instead of
jumping.

### Image matching

Every image step, checker branch and overseer has a **Match at least (%)** setting.
The default is 80%, so small changes in lighting, animation or anti-aliasing still
match. Lower it if something is missed; raise it if the wrong thing is found. Crop
images tightly around something that always looks the same.

## Zips and sharing

| Folder | What's in it |
|---|---|
| `flows/<macro>/` | Your macros: `flow.json` plus `images/` |
| `library/<node>.zip` | Reusable nodes. A node is saved here automatically when you stop recording it, or when you press **Save to library**. Add one to any macro with **+ From library**. |
| `exports/<macro>.zip` | Whole macros to share. Made by **Export zip** and whenever you close the editor. |

Every zip contains the JSON, the images it needs, and an `INSTRUCTIONS.md` that lists
every step in plain words. Import any of them in **Input** mode: a macro zip goes into
your runnable list, and a node zip goes into the library.

## Python macros (advanced)

`.py` files in `macros/` also show up in Macro mode. See [MACROS.md](MACROS.md).

## Code layout

```
main.py                entry point
aamacro/config.py      frame size, hotkeys, match level, mouse speed
aamacro/ui.py          border overlay and the side panel's modes
aamacro/editor.py      Create mode editor window
aamacro/recorder.py    \ [ ] recording
aamacro/flow.py        macro data, validation, zips, instructions
aamacro/engine.py      plays nodes, checkers and overseers
aamacro/api.py         the `m` object (input + vision) used by everything
aamacro/inputs.py      keyboard/mouse via SendInput (scan codes, which Roblox reads)
aamacro/vision.py      screen capture (mss) and image/colour search (OpenCV)
aamacro/win32.py       finding, sizing and focusing the Roblox window
```
