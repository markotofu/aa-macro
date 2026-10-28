"""Basics: clicking, keys, camera and waiting.

Coordinates are pixels inside the 800x600 frame; (0, 0) is the game's top-left.
Hover over the game and read "Mouse x, y" in the panel to find them.
"""


def run(m):
    m.log("Hello from example_basics")

    m.click(400, 300)          # click the middle of the game
    m.wait(0.5)

    m.press("w", hold=1.5)     # walk forward for 1.5 seconds
    m.press("space")           # jump
    m.wait(0.5)

    # Turn the camera: hold right mouse and move the mouse sideways.
    m.mouse_down("right")
    m.move_by(300, 0, duration=0.4)
    m.mouse_up("right")

    m.scroll(-3)               # zoom the camera out
    m.log("Pixel colour in the middle:", m.pixel(400, 300))
