"""OpenCV, with an error that says what to do when it cannot load. The GUI build `opencv-python`
and `opencv-python-headless` both install the `cv2` module; whichever was installed last wins, and
the GUI build fails on a server without X libraries (libxcb, libGL)."""

import importlib.metadata

from .errors import BoxError

GUI_BUILDS = ("opencv-python", "opencv-contrib-python")


def _installed(name: str) -> bool:
    try:
        importlib.metadata.version(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


def explain(err: ImportError, installed=_installed) -> BoxError:
    gui = [name for name in GUI_BUILDS if installed(name)]
    if gui:
        fix = f"pip uninstall -y {' '.join(gui)} && pip install --force-reinstall --no-deps opencv-python-headless"
        message = (f"OpenCV cannot load ({err}). {' and '.join(gui)} is installed next to or instead of "
                   f"opencv-python-headless and needs a desktop's libraries; keep only the headless build: {fix}")
    else:
        message = f"OpenCV cannot load ({err}); reinstall it: pip install --force-reinstall --no-deps opencv-python-headless"
    return BoxError("opencv_unavailable", message, gui_builds=gui)


try:
    import cv2
except ImportError as _err:
    raise explain(_err) from None
