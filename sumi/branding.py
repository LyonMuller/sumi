"""Application identity and window icon; no changes to system-wide settings."""
import os
import tkinter as tk
from .paths import resource_root

ICON=resource_root()/'assets'/'brand'/'app-icon.ico'
PNG_ICON=resource_root()/'assets'/'brand'/'app-icon.png'


def set_process_identity() -> None:
    if os.name=='nt':
        import ctypes
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Sumi.Desktop')
        except (OSError,AttributeError):
            pass


def set_window_icon(window:tk.Tk | tk.Toplevel) -> None:
    if os.name!='nt':
        # .ico is Windows-only. A PNG photo sets the Dock icon when running from sources.
        if PNG_ICON.is_file() and isinstance(window,tk.Tk):
            try:
                window._icon_photo=tk.PhotoImage(master=window,file=str(PNG_ICON))  # type: ignore[attr-defined]
                window.iconphoto(True,window._icon_photo)  # type: ignore[attr-defined]
            except (tk.TclError,OSError):
                pass
        return
    if ICON.is_file():
        try:
            # CustomTkinter sees this explicit call and retains our icon after its startup timer.
            window.iconbitmap(default=str(ICON))
        except (tk.TclError,OSError):
            pass
