"""Screen capture plus image and colour search (mss + OpenCV + numpy).

Images are numpy arrays in OpenCV's BGR channel order; colours passed in and
out of this module are (r, g, b) tuples.
"""
import threading
from pathlib import Path

import cv2
import mss
import numpy as np

_local = threading.local()
_template_cache = {}


def _grabber():
    # mss handles are not safe to share between threads.
    if not hasattr(_local, "sct"):
        _local.sct = mss.MSS()
    return _local.sct


def grab(rect):
    """Capture a screen Rect as a BGR image."""
    shot = _grabber().grab({"left": rect.left, "top": rect.top,
                            "width": rect.width, "height": rect.height})
    return np.ascontiguousarray(np.asarray(shot)[:, :, :3])


def read_image(path):
    # imdecode instead of imread so non-ASCII Windows paths work.
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"{path} is not a readable image")
    return img


def write_image(path, img):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, data = cv2.imencode(path.suffix or ".png", img)
    if not ok:
        raise ValueError(f"Could not encode {path}")
    data.tofile(str(path))


def load_template(path):
    """Read an image file, reusing the cached copy until the file changes."""
    path = Path(path)
    mtime = path.stat().st_mtime
    cached = _template_cache.get(path)
    if cached and cached[0] == mtime:
        return cached[1]
    img = read_image(path)
    _template_cache[path] = (mtime, img)
    return img


def _scores(haystack, template):
    """Similarity map where 1.0 is a perfect match at that top-left corner."""
    if template.reshape(-1, template.shape[2]).std(axis=0).max() < 1:
        # Flat single-colour templates make the normalised correlation divide
        # by zero, so score them by squared difference instead.
        return 1 - cv2.matchTemplate(haystack, template, cv2.TM_SQDIFF_NORMED)
    result = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
    return np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)


def match_best(haystack, template, confidence):
    """(x, y, score) of the best match at or above confidence, else None."""
    th, tw = template.shape[:2]
    if th > haystack.shape[0] or tw > haystack.shape[1]:
        return None
    _, score, _, (x, y) = cv2.minMaxLoc(_scores(haystack, template))
    return (x, y, float(score)) if score >= confidence else None


def match_all(haystack, template, confidence, limit=100):
    """Every non-overlapping (x, y, score) at or above confidence, best first."""
    th, tw = template.shape[:2]
    if th > haystack.shape[0] or tw > haystack.shape[1]:
        return []
    scores = _scores(haystack, template)
    ys, xs = np.where(scores >= confidence)
    order = np.argsort(-scores[ys, xs])
    picked = []
    for i in order:
        x, y = int(xs[i]), int(ys[i])
        if all(abs(x - px) >= tw // 2 or abs(y - py) >= th // 2 for px, py, _ in picked):
            picked.append((x, y, float(scores[y, x])))
            if len(picked) >= limit:
                break
    return picked


def color_mask(img, rgb, tolerance):
    """Boolean mask of pixels within `tolerance` of rgb on every channel."""
    target = np.array(rgb[::-1], dtype=np.int16)  # to BGR
    return np.all(np.abs(img.astype(np.int16) - target) <= tolerance, axis=2)


def find_color(img, rgb, tolerance):
    """(x, y) of the first pixel matching the colour (top-to-bottom), else None."""
    hits = np.argwhere(color_mask(img, rgb, tolerance))
    if len(hits) == 0:
        return None
    y, x = hits[0]
    return int(x), int(y)
