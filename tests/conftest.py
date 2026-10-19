"""Use one Tk interpreter, matching the application's desktop lifecycle."""
import sys

import pytest


@pytest.fixture(scope="session")
def _desktop_session():
    if sys.platform != "win32":
        pytest.skip("Windows desktop UI")
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def desktop_root(_desktop_session):
    root = _desktop_session
    existing_timers = set(root.tk.call("after", "info"))
    yield root
    for timer in set(root.tk.call("after", "info")) - existing_timers:
        root.after_cancel(timer)
    for child in tuple(root.winfo_children()):
        child.destroy()
    root.update_idletasks()
