# AA Macro

A programmable Roblox macro tool for Windows that behaves the same on any screen size.

It finds the Roblox window and resizes its game area to a fixed **1024 × 576** frame,
then draws a green border around it and docks a control panel beside it. All clicks,
mouse moves and image searches use coordinates inside that frame. A macro you write
on a 4K monitor therefore works on a 1366×768 laptop.

## Setup

Requires Windows and Python 3.10 or newer.

```bash
python -m venv .venv
```

```bash
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run

Start Roblox (windowed, not F11 fullscreen), then double-click `run.bat`, or run:

```bash
.venv\Scripts\python main.py
```

The frame snaps onto Roblox automatically. With **Keep size locked** on, it snaps
back if the window gets resized. Moving the Roblox window moves the border and panel too.

| Key | Action |
|---|---|
| F6 | Run the selected macro, or stop it |
| F7 | Stop the macro |
| F8 | Exit the app immediately |

## Panel

- **Snap to Roblox** resizes the game area to the frame size.
- **Macro** lists the files in `macros/`. **Run** and **Stop** control them.
- **Capture image…** freezes the game. Drag a box to save a picture into `images/` for macros to look for.
- **Save screenshot** saves the whole frame to `screenshots/`.
- **Mouse / RGB** shows the cursor's frame coordinate and the colour under it, for writing macros.
- **Log** shows macro output and errors.

## Writing macros

See [MACROS.md](MACROS.md). In short, add `macros/anything.py` containing:

```python
def run(m):
    m.click(512, 288)
    outcome, _ = m.wait_for_any({"win": "victory", "lose": "defeat"}, timeout=300)
    if outcome == "win":
        m.click_image("next")
```

## Layout

```
main.py              entry point
aamacro/config.py    frame size, hotkeys, default confidence
aamacro/ui.py        border overlay, side panel, capture tool
aamacro/api.py       the `m` object macros use
aamacro/inputs.py    keyboard/mouse via SendInput (scan codes, which Roblox reads)
aamacro/vision.py    screen capture (mss) and image/colour search (OpenCV)
aamacro/win32.py     finding, sizing and focusing the Roblox window
macros/              your macros
images/              pictures macros search for
```
