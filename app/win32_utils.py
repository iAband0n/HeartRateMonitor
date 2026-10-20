"""Small Win32 helpers used by the overlay windows.

The overlay relies on native window styles in addition to Qt's flags:

* ``WS_EX_NOACTIVATE`` keeps the overlay from stealing focus from a game.
* ``WS_EX_TOOLWINDOW`` hides it from Alt+Tab.
* ``WS_EX_TRANSPARENT`` gives click-through when locked.
* ``SetWindowPos(HWND_TOPMOST, ...)`` is repeated on a timer because some
  fullscreen/windowed-fullscreen applications re-order their own window.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import sys

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SWP_NOOWNERZORDER = 0x0200

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_DPICHANGED = 0x02E0
WM_DISPLAYCHANGE = 0x007E

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        _get_long = user32.GetWindowLongPtrW
        _set_long = user32.SetWindowLongPtrW
        _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        _get_long.restype = ctypes.c_ssize_t
        _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        _set_long.restype = ctypes.c_ssize_t
    except AttributeError:  # pragma: no cover - 32-bit fallback
        _get_long = user32.GetWindowLongW
        _set_long = user32.SetWindowLongW
        _get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        _get_long.restype = ctypes.c_long
        _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        _set_long.restype = ctypes.c_long

    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL

    user32.GetForegroundWindow.restype = wintypes.HWND

    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL


def hwnd_of(widget) -> int:
    try:
        return int(widget.winId())
    except Exception:
        return 0


def get_ex_style(hwnd: int) -> int:
    if not IS_WINDOWS or not hwnd:
        return 0
    return int(_get_long(wintypes.HWND(hwnd), GWL_EXSTYLE))


def set_ex_style(hwnd: int, style: int) -> None:
    if not IS_WINDOWS or not hwnd:
        return
    _set_long(wintypes.HWND(hwnd), GWL_EXSTYLE, style)


def keep_topmost(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
    return bool(user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST), 0, 0, 0, 0, flags))


def apply_overlay_styles(hwnd: int, locked: bool, topmost: bool = True) -> None:
    """Apply tool/no-activate/click-through styles and re-assert topmost."""
    if not IS_WINDOWS or not hwnd:
        return
    style = get_ex_style(hwnd)
    style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    if locked:
        style |= WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
    set_ex_style(hwnd, style)
    if topmost:
        keep_topmost(hwnd)


def set_click_through(hwnd: int, enabled: bool) -> None:
    if not IS_WINDOWS or not hwnd:
        return
    style = get_ex_style(hwnd)
    if enabled:
        style |= WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
    set_ex_style(hwnd, style)


def is_click_through(hwnd: int) -> bool:
    return bool(get_ex_style(hwnd) & WS_EX_TRANSPARENT)


def register_hotkey(hwnd: int, hotkey_id: int, modifiers: int, virtual_key: int) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        ok = bool(
            user32.RegisterHotKey(
                wintypes.HWND(hwnd),
                hotkey_id,
                modifiers | MOD_NOREPEAT,
                virtual_key,
            )
        )
        if not ok:
            log.warning(
                "RegisterHotKey failed (id=%s, err=%s)",
                hotkey_id,
                ctypes.get_last_error(),
            )
        return ok
    except Exception:
        log.exception("RegisterHotKey crashed")
        return False


def unregister_hotkey(hwnd: int, hotkey_id: int) -> None:
    if not IS_WINDOWS or not hwnd:
        return
    try:
        user32.UnregisterHotKey(wintypes.HWND(hwnd), hotkey_id)
    except Exception:
        pass


def set_app_user_model_id(app_id: str = "W.HeartRateOverlay.1") -> None:
    if not IS_WINDOWS:
        return
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [wintypes.LPCWSTR]
        shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass


def open_folder(path: str) -> None:
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except Exception:
        log.exception("Could not open folder %s", path)
