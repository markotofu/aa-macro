from aamacro import win32

# Must happen before any window exists so every coordinate is a physical pixel.
win32.enable_dpi_awareness()

from aamacro.ui import App  # noqa: E402

if __name__ == "__main__":
    App().run()
