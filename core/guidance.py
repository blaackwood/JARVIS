"""State and input verification for JARVIS-guided guided screen steps."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class GuidanceTarget:
    rect: tuple[int,int,int,int]
    label: str
    app: str
    title: str
    pid: int
    step: int
    created_at: float
    role: str = ""


_lock=threading.RLock()
_target: GuidanceTarget|None=None


def set_target(rect, label: str, app: str="", title: str="", pid: int=0,
               step: int=1, role: str="") -> GuidanceTarget:
    global _target
    if not isinstance(rect,(tuple,list)) or len(rect)!=4:
        raise ValueError("target bounds must be [left, top, width, height]")
    x,y,w,h=(int(round(float(v))) for v in rect)
    if w<=0 or h<=0:
        raise ValueError("target has no visible area")
    target=GuidanceTarget((x,y,w,h),str(label or "")[:100],
                          str(app or "")[:100],str(title or "")[:160],
                          int(pid or 0),max(1,min(99,int(step or 1))),
                          time.monotonic(),str(role or "")[:40])
    with _lock:
        _target=target
    return target


def get_target() -> GuidanceTarget|None:
    with _lock:
        return _target


def clear_target() -> GuidanceTarget|None:
    global _target
    with _lock:
        old=_target
        _target=None
    return old


def point_inside(rect, point) -> bool:
    x,y,w,h=(float(v) for v in rect)
    px,py=(float(v) for v in point)
    return x<=px<=x+w and y<=py<=y+h


def wait_for_user_click(target: GuidanceTarget, timeout: float=120.0,
                        poll=None, cancel=None, interval: float=0.025,
                        clock=time.monotonic, sleep=time.sleep) -> dict:
    """Wait for a new left-button press inside the currently highlighted UIA rectangle.

    This is an observed physical click, not proof that the application accepted
    the action. A caller must still inspect the resulting UI state.
    """
    if poll is None:
        raise ValueError("a mouse-state poller is required")
    deadline=clock()+max(0.1,min(float(timeout),300.0))
    # A mouse button already held when the wait begins is not the user's next
    # click; require a release followed by a fresh press.
    try:
        was_down=bool((poll() or {}).get("down"))
    except Exception:
        was_down=False
    while clock()<deadline:
        if cancel and cancel():
            return {"status":"cancelled","target":target.label}
        state=poll() or {}
        down=bool(state.get("down"))
        point=(state.get("x",0),state.get("y",0))
        if down and not was_down and point_inside(target.rect,point):
            return {
                "status":"clicked",
                "target":target.label,
                "point":[int(point[0]),int(point[1])],
                "elapsed":round(max(0.0,clock()-target.created_at),2),
            }
        was_down=down
        sleep(max(0.005,min(float(interval),0.2)))
    return {"status":"timeout","target":target.label}


def wait_for_user_hover(target: GuidanceTarget, timeout: float=120.0,
                        poll=None, cancel=None, interval: float=0.025,
                        dwell: float=0.45, clock=time.monotonic,
                        sleep=time.sleep) -> dict:
    """Wait for a fresh, unpressed pointer entry that stays over a target for a dwell."""
    if poll is None:
        raise ValueError("a mouse-state poller is required")
    deadline=clock()+max(0.1,min(float(timeout),300.0))
    dwell=max(0.1,min(float(dwell),3.0))
    # Require the pointer to enter after this wait starts; already hovering does not count.
    was_inside=False
    hover_since=None
    last_point=(0,0)
    while clock()<deadline:
        if cancel and cancel():
            return {"status":"cancelled","target":target.label}
        state=poll() or {}
        point=(state.get("x",0),state.get("y",0))
        last_point=point
        inside=point_inside(target.rect,point) and not bool(state.get("down"))
        if inside and not was_inside:
            hover_since=clock()
        elif not inside:
            hover_since=None
        if inside and hover_since is not None and clock()-hover_since>=dwell:
            return {
                "status":"hovered",
                "target":target.label,
                "point":[int(point[0]),int(point[1])],
                "dwell":round(dwell,2),
                "elapsed":round(max(0.0,clock()-target.created_at),2),
            }
        was_inside=inside
        sleep(max(0.005,min(float(interval),0.2)))
    return {"status":"timeout","target":target.label,"point":[int(last_point[0]),int(last_point[1])]}


def windows_mouse_poll() -> dict:
    """Read one global left-button edge and cursor position without intercepting input."""
    if __import__("platform").system()!="Windows":
        raise RuntimeError("global mouse polling is available only on Windows")
    import ctypes

    class POINT(ctypes.Structure):
        _fields_=[("x",ctypes.c_long),("y",ctypes.c_long)]
    user32=ctypes.windll.user32
    p=POINT()
    if not user32.GetCursorPos(ctypes.byref(p)):
        return {"down":False,"x":0,"y":0}
    # screenview's UIA rectangles and screenact's mouse operations share the
    # same logical coordinate space. GetCursorPos is physical, so apply the
    # exact scale factor used by the accessibility reader.
    try:
        from core.screenview import _physical_to_logical
        scale=float(_physical_to_logical())
    except Exception:
        scale=1.0
    return {
        "down":bool(user32.GetAsyncKeyState(0x01)&0x8000),
        "x":round(int(p.x)*scale),"y":round(int(p.y)*scale),
    }


def windows_escape_down() -> bool:
    if __import__("platform").system()!="Windows":
        return False
    import ctypes
    return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B)&0x8000)
