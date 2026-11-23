"""Native Win32 notification-area icon for the lightweight wake daemon.

Uses only ctypes and user32/shell32; deliberately avoids Qt and a GUI toolkit.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadIconW.restype = wintypes.HICON
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.RegisterClassW.restype = wintypes.ATOM
user32.GetMessageW.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.restype = wintypes.BOOL

WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_CLOSE = 0x0010
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_LBUTTONDBLCLK = 0x0203
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x0010
IDI_APPLICATION = 32512
MF_STRING, MF_SEPARATOR = 0, 0x0800
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100
GWLP_USERDATA = -21
ID_OPEN, ID_EXIT = 1001, 1002
TIMER_ID = 1


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD), ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT), ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD), ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    pass


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)
WNDCLASSW._fields_ = [
    ("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
]


user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
user32.SetTimer.restype = ctypes.c_size_t
user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, wintypes.HWND, wintypes.LPVOID]
user32.TrackPopupMenu.restype = wintypes.UINT
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]

class WakeTray:
    def __init__(self, icon_path: Path, on_open, on_exit, on_tick):
        self.on_open = on_open
        self.on_exit = on_exit
        self.on_tick = on_tick
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.class_name = "JarvisWakeNativeTrayWindow"
        self.icon = user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 0, 0,
                                      LR_LOADFROMFILE)
        if not self.icon:
            self.icon = user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
        self._wndproc = WNDPROC(self._window_proc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc
        wc.hInstance = self.hinstance
        wc.lpszClassName = self.class_name
        atom = user32.RegisterClassW(ctypes.byref(wc))
        if not atom and ctypes.get_last_error() != 1410:
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd = user32.CreateWindowExW(
            0, self.class_name, "JARVIS Wake Listener", 0,
            0, 0, 0, 0, None, None, self.hinstance, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.nid = NOTIFYICONDATAW()
        self.nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self.nid.hWnd = self.hwnd
        self.nid.uID = 1
        self.nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self.nid.uCallbackMessage = WM_TRAY
        self.nid.hIcon = self.icon
        self.set_tooltip("JARVIS â€” hibernado, aguardando Hey Jarvis")
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self.nid)):
            raise ctypes.WinError(ctypes.get_last_error())
        user32.SetTimer(self.hwnd, TIMER_ID, 200, None)

    def set_tooltip(self, value: str):
        self.nid.szTip = value[:127]
        self.nid.uFlags = NIF_TIP | NIF_ICON | NIF_MESSAGE
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self.nid))

    def _show_menu(self):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, ID_OPEN, "Abrir JARVIS")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_EXIT, "Sair completamente")
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)
        selected = user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
            point.x, point.y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)
        if selected == ID_OPEN:
            self.on_open()
        elif selected == ID_EXIT:
            self.on_exit()

    def _window_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            event = lparam & 0xFFFF
            if event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu()
            elif event == WM_LBUTTONDBLCLK:
                self.on_open()
            return 0
        if msg == WM_COMMAND:
            return 0
        if msg == WM_TIMER and wparam == TIMER_ID:
            self.on_tick()
            return 0
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_DESTROY:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def run(self):
        msg = wintypes.MSG()
        while True:
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        return int(msg.wParam)

    def close(self):
        if self.hwnd:
            user32.KillTimer(self.hwnd, TIMER_ID)
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self.icon:
            user32.DestroyIcon(self.icon)
            self.icon = None


