"""Traz janelas do Windows para frente (usado pelo HUD e pelo Agent UI)."""
import ctypes
from ctypes import wintypes as wt


def focus_window(match):
    """Traz para frente a primeira janela visivel com match(pid, titulo) verdadeiro."""
    u = ctypes.windll.user32
    found = []
    cb_t = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                pid = wt.DWORD()
                u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if match(pid.value, buf.value):
                    found.append(hwnd)
                    return False
        return True

    u.EnumWindows(cb_t(cb), 0)
    if not found:
        return False
    h = found[0]
    if u.IsIconic(h):
        u.ShowWindow(h, 9)
    u.keybd_event(0x12, 0, 0, 0)  # Alt: libera o SetForegroundWindow
    u.keybd_event(0x12, 0, 2, 0)
    u.SetForegroundWindow(h)
    return True
