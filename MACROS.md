# Writing Python macros

> Most macros are easier to build in **Create mode** without code (see README.md).
> Python macros are the advanced option, for logic the editor can't express.


A macro is a Python file in `macros/` with one function, `run(m)`. When you press
**Run** (or F6), the app brings Roblox to the front and calls `run(m)`. The `m`
object does everything: clicks, keys, waiting, and looking at the screen. Because
it's plain Python, you can use `if`, `for`, `while`, variables and functions to
build any logic you want. The macro runs on its own and never waits on you.

```python
# macros/my_macro.py
def run(m):
    m.click(400, 300)
    m.press("w", hold=2)
    if m.wait_for_image("victory", timeout=60):
        m.log("won")
```

Edits take effect the next time you press Run, so there's no need to restart the app.
Files starting with `_` (like `_template.py`) don't show up in the list.

## Coordinates

Every position is a pixel **inside the frame**. `(0, 0)` is the top-left of the game
area and `(799, 599)` is the bottom-right (the size is set in `aamacro/config.py`).
The frame is always resized to exactly this size, so the same numbers hit the same
spot on any monitor, at any resolution or Windows scaling. Points outside the frame
are refused with an error.

To find a coordinate, hover over the game. The panel shows `Mouse x, y` and the
pixel's `RGB` colour.

Anywhere a point is expected you can pass `x, y`, a tuple `(x, y)`, or a `Match`
returned by an image search (its centre is used).

A **region** is `(x, y, width, height)` inside the frame. It limits an image or colour
search to part of the screen, which is faster and avoids false matches.

## Images

1. Get the game showing the thing you want to detect.
2. In **Macro** mode, click **Capture image for .py macros…**. The game freezes under a crosshair.
3. Drag a box around the thing and give it a name, for example `play_button`.
4. It is saved as `images/play_button.png`, and the log prints its region.

Use it in a macro by name: `m.find_image("play_button")`. Tips:

- Crop tightly around something that always looks the same. Leave out changing
  numbers, animated parts and the 3D world behind it.
- `confidence` (0 to 1, default 0.8) is how exact the match must be. Lower it
  (e.g. 0.7) if a match is missed; raise it if the wrong thing is found.
- For one solid colour, `find_color` / `color_matches` are faster than an image.

## Branching on what's on screen

`wait_for_any` waits for several possibilities at once and tells you which one
showed up first. You decide what the macro does on each path:

```python
outcome, match = m.wait_for_any({"win": "victory", "lose": "defeat"}, timeout=600)
if outcome == "win":
    m.click_image("next_stage")
elif outcome == "lose":
    m.click_image("retry")
else:                       # None: nothing appeared before the timeout
    m.save_screenshot("stuck")
    return                  # ends the macro
```

An option can also be a function that returns true or false, for checks that aren't images:

```python
outcome, _ = m.wait_for_any({
    "boss": "boss_health_bar",
    "low_hp": lambda: m.color_matches(80, 40, (200, 30, 30)),
}, timeout=120)
```

## Command reference

### Mouse
| Command | What it does |
|---|---|
| `m.click(x, y)` | Left click at a point. `button="right"`, `clicks=2` are optional. With no point it clicks where the cursor is. |
| `m.right_click(x, y)` / `m.double_click(x, y)` | Shortcuts for the above. |
| `m.move(x, y)` | Move the cursor to a point. |
| `m.drag((x1, y1), (x2, y2), duration=0.3)` | Press, glide, release. |
| `m.mouse_down("left")` / `m.mouse_up("left")` | Hold or release a button (`"left"`, `"right"`, `"middle"`). |
| `m.move_by(dx, dy, duration=0)` | Raw relative movement. Hold the right button first to turn the camera. |
| `m.scroll(n)` | Mouse wheel. Positive is up (zoom in), negative is down. |
| `m.mouse_position()` | Cursor `(x, y)` in the frame, or `None` if outside it. |

### Keyboard
| Command | What it does |
|---|---|
| `m.press("e")` | Tap a key. `hold=2` holds it for 2 seconds, which is how you walk. |
| `m.key_down("w")` / `m.key_up("w")` | Hold or release a key. |
| `m.hotkey("shift", "w")` | Press keys together. |
| `m.type("gg")` | Type text (open chat with `m.press("/")` first). |

Key names include the letters, digits and symbols, plus `space`, `enter`, `tab`, `esc`,
`backspace`, `shift`, `ctrl`, `alt`, `up`, `down`, `left`, `right`, `f1` to `f24`,
`num0` to `num9`, `home`, `end`, `pageup`, `pagedown`, `insert`, `delete`.

### Screen
| Command | What it does |
|---|---|
| `m.find_image("name", region=None, confidence=None)` | Look once. Returns a `Match` or `None`. |
| `m.image_exists("name")` | `True` or `False`. |
| `m.wait_for_image("name", timeout=10)` | Keep looking. Returns a `Match` or `None`. |
| `m.wait_for_image_gone("name", timeout=10)` | `True` once the image disappears. |
| `m.click_image("name", timeout=0, offset=(0, 0))` | Find it and click its centre. Returns the `Match` or `None`. |
| `m.find_all_images("name")` | A list of every match, best first. |
| `m.wait_for_any({...}, timeout=10)` | Returns `(label, match)` or `(None, None)`. See above. |
| `m.pixel(x, y)` | `(r, g, b)` at a point. |
| `m.color_matches(x, y, (r, g, b), tolerance=10)` | `True` if that pixel is that colour. |
| `m.find_color((r, g, b), region=None, tolerance=10)` | First `(x, y)` with that colour, or `None`. |
| `m.wait_for_color(x, y, (r, g, b), timeout=10)` | `True` once the pixel turns that colour. |
| `m.screenshot(region=None)` | The frame as a numpy (OpenCV BGR) image for custom checks. |
| `m.save_screenshot("name")` | Save to `screenshots/name.png`. |

A `Match` has `.x .y .width .height` (its top-left and size), `.center`, and `.score`.

### Flow
| Command | What it does |
|---|---|
| `m.wait(seconds)` | Pause. Stops immediately if you press Stop. |
| `m.wait_until(func, timeout=10)` | Wait until `func()` returns something truthy. Returns that value, or `None` on timeout. |
| `m.log("text", value)` | Print a line to the panel's log. |
| `m.focus()` | Bring Roblox to the front (done automatically at start). |
| `m.check()` | Ends the macro if Stop was pressed. Call it inside loops that don't use any `m.` commands. |
| `m.width`, `m.height` | Frame size. |

## Stopping

- **F7** or **Stop** ends the running macro at its next `m.` command. Held keys and buttons are released.
- **F6** runs the selected macro, or stops it if one is running.
- **F8** kills the whole app instantly, from anywhere.

If a macro errors, the log shows the message and the line number in your file.
