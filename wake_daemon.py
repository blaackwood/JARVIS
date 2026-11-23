"""Low-footprint Hey Jarvis listener with a persistent Windows tray icon.

The daemon owns the microphone only while the full assistant is hibernated.
The Qt tray runs on the main thread; wake-word audio inference runs on a
background thread. The icon remains available while the assistant sleeps.
"""
from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

# Keep every helper launched by the always-on listener free of console windows.
from core.windows_process import install_no_console_policy
install_no_console_policy()

# Keep native math runtimes from creating a large worker pool on a tiny
# always-on listener. LiteRT itself is configured for one inference thread.
for _thread_env in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                    "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_thread_env, "1")

import numpy as np
import sounddevice as sd
import types

# Prefer Google's lightweight LiteRT runtime over ONNX Runtime for the
# always-on wake model. openWakeWord still supplies the same model and DSP
# pipeline; this compatibility shim only maps its expected import name.
try:
    from ai_edge_litert import interpreter as _litert_interpreter
    _tflite_runtime = types.ModuleType("tflite_runtime")
    _tflite_runtime.__path__ = []
    _tflite_runtime.interpreter = _litert_interpreter
    sys.modules["tflite_runtime"] = _tflite_runtime
    sys.modules["tflite_runtime.interpreter"] = _litert_interpreter
    WAKE_FRAMEWORK = "tflite"
except ImportError:
    WAKE_FRAMEWORK = "onnx"

from openwakeword.model import Model
from core.wake_startup import clear_stale_stop_marker
from core.wake_tray_win32 import WakeTray

BASE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
JARVIS_EXE = BASE / "JARVIS.exe"
PYTHON = (BASE / ".venv" / "Scripts" / "pythonw.exe") if not getattr(sys, "frozen", False) else Path(sys.executable)
LOG = BASE / "memory" / "wake_daemon.log"
STOP = BASE / "memory" / "wake_daemon.stop"
ICON = BASE / "config" / "jarvis.ico"
SAMPLE_RATE = 16000
BLOCK = 1280
THRESHOLD = 0.62
REQUIRED_HITS = 3
MUTEX_NAME = r"Global\JarvisWakeDaemon"

events: queue.Queue[str] = queue.Queue()
stop_event = threading.Event()
listener_thread: threading.Thread | None = None
child_process: subprocess.Popen | None = None
mutex = None


def log(message: str) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


def acquire_single_instance():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        raise OSError("Could not create wake daemon mutex")
    if ctypes.get_last_error() == 183:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return None
    return (kernel32, handle)


def lower_background_priority() -> None:
    """Keep the always-on wake listener below games and foreground apps."""
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel32.SetPriorityClass.restype = ctypes.c_bool
        # BELOW_NORMAL_PRIORITY_CLASS: games and interactive applications win CPU time.
        if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x00004000):
            log(f"could not lower process priority (winerr={ctypes.get_last_error()})")
    except Exception as exc:
        log(f"could not lower process priority: {type(exc).__name__}: {exc}")


def lower_listener_thread_priority() -> None:
    """Make ONNX inference yield to foreground/game threads."""
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentThread.restype = ctypes.c_void_p
        kernel32.SetThreadPriority.argtypes = [ctypes.c_void_p, ctypes.c_int]
        kernel32.SetThreadPriority.restype = ctypes.c_bool
        # THREAD_PRIORITY_BELOW_NORMAL = -1. Audio capture remains blocking and responsive.
        if not kernel32.SetThreadPriority(kernel32.GetCurrentThread(), -1):
            log(f"could not lower listener thread priority (winerr={ctypes.get_last_error()})")
    except Exception as exc:
        log(f"could not lower listener thread priority: {type(exc).__name__}: {exc}")


def task_worker_mutex_exists() -> bool:
    """Whether a task worker still owns its single-instance mutex.

    The PID marker can survive a power loss or forced process termination.
    The named mutex cannot: Windows releases it when the owning process exits.
    This lets the wake daemon distinguish a live worker from a stale marker.
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenMutexW(0x00100000, False,
                                 r"Global\JarvisTaskWorker")
    if not handle:
        return False
    kernel32.CloseHandle(ctypes.c_void_p(handle))
    return True


def wait_for_pid_exit(pid: int) -> bool:
    """Wait until the full JARVIS process releases the microphone, or exit is requested."""
    if pid <= 0:
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return True
    try:
        while not stop_event.is_set() and not STOP.exists():
            result = kernel32.WaitForSingleObject(handle, 500)
            if result == 0:       # WAIT_OBJECT_0: parent exited
                return True
            if result == 0xFFFFFFFF:  # WAIT_FAILED: treat an invalid PID as gone
                return True
        return False
    finally:
        kernel32.CloseHandle(handle)


def listen_worker(parent_pid: int = 0) -> None:
    lower_listener_thread_priority()
    if parent_pid and not wait_for_pid_exit(parent_pid):
        log("parent wait cancelled; microphone was not opened")
        return
    while not stop_event.is_set() and not STOP.exists():
        try:
            log("hibernated listener starting")
            model = Model(wakeword_models=["hey_jarvis"], inference_framework=WAKE_FRAMEWORK)
            log(f"wake model loaded on CPU ({"LiteRT" if WAKE_FRAMEWORK == "tflite" else "ONNX fallback"})")
            hits = 0
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE, blocksize=BLOCK, channels=1,
                dtype="int16", latency="high",
            ) as stream:
                log("microphone listener active")
                while not stop_event.is_set() and not STOP.exists():
                    audio, overflowed = stream.read(BLOCK)
                    if overflowed:
                        continue
                    scores = model.predict(np.frombuffer(audio, dtype=np.int16))
                    score = max((float(v) for k, v in scores.items()
                                 if "jarvis" in k.lower()), default=0.0)
                    hits = hits + 1 if score >= THRESHOLD else 0
                    if hits >= REQUIRED_HITS:
                        log(f"wake detected score={score:.3f}")
                        events.put("wake")
                        return
        except Exception as exc:
            log(f"microphone/listener error: {type(exc).__name__}: {exc}")
            if not stop_event.is_set() and not STOP.exists():
                stop_event.wait(3.0)
    log("listener stopped")


def start_listener(parent_pid: int = 0) -> None:
    global listener_thread
    if listener_thread and listener_thread.is_alive():
        return
    stop_event.clear()
    listener_thread = threading.Thread(
        target=listen_worker, args=(parent_pid,), name="JarvisWakeAudio", daemon=True
    )
    listener_thread.start()


def main() -> int:
    global mutex, child_process
    if os.name != "nt":
        log("unsupported platform")
        return 2
    lower_background_priority()
    mutex = acquire_single_instance()
    if mutex is None:
        log("another daemon already owns the wake listener; exiting")
        return 0
    parent_pid = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if parent_pid == 0 and not clear_stale_stop_marker(STOP):
        log("could not clear stale stop marker; daemon will not listen")
        return 1
    if STOP.exists():
        log("stop marker present; daemon will not listen")
        return 0

    tray = None

    def launch_jarvis():
        global child_process
        if child_process is not None and child_process.poll() is None:
            return
        stop_event.set()
        if tray:
            tray.set_tooltip("JARVIS — retomando")
            tray.hide()
        try:
            if listener_thread and listener_thread.is_alive():
                listener_thread.join(timeout=2.0)
            worker_pid = BASE / "memory" / "task_worker.pid"
            worker_stop = BASE / "memory" / "task_worker.stop"
            worker_stop.parent.mkdir(parents=True, exist_ok=True)
            worker_stop.write_text("stop", encoding="ascii")
            if worker_pid.exists() and not task_worker_mutex_exists():
                worker_pid.unlink(missing_ok=True)
                log("removed stale task worker PID marker; no worker owns the mutex")
            deadline = time.monotonic() + 70.0
            while worker_pid.exists() and time.monotonic() < deadline:
                time.sleep(0.25)
            if worker_pid.exists():
                log("task worker did not release its store within 70s; refusing duplicate engine launch")
                events.put("resume")
                return
            command = ([str(JARVIS_EXE), "--wake-daemon-child"] if getattr(sys, "frozen", False)
                       else [str(PYTHON), str(BASE / "main.py"), "--wake-daemon-child"])
            child_process = subprocess.Popen(
                command, cwd=str(BASE),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            log(f"JARVIS launched pid={child_process.pid}")
            def watch_child(proc):
                proc.wait()
                events.put("exit" if STOP.exists() else "resume")
            threading.Thread(target=watch_child, args=(child_process,),
                             name="JarvisChildWait", daemon=True).start()
        except Exception as exc:
            log(f"launch failed: {type(exc).__name__}: {exc}")
            events.put("resume")

    def exit_completely():
        try:
            STOP.parent.mkdir(parents=True, exist_ok=True)
            STOP.write_text("stop\n", encoding="utf-8")
        except Exception as exc:
            log(f"could not write stop marker: {exc}")
        try:
            worker_dir = BASE / "memory"
            (worker_dir / "task_worker.cancel").write_text("cancel", encoding="ascii")
            (worker_dir / "task_worker.stop").write_text("stop", encoding="ascii")
        except Exception as exc:
            log(f"could not signal task worker exit: {exc}")
        stop_event.set()
        log("user requested complete exit from tray")
        if tray:
            tray.close()

    def poll_events():
        global child_process
        if STOP.exists():
            stop_event.set()
            if child_process is None or child_process.poll() is not None:
                log("stop marker observed; daemon exiting")
                if tray:
                    tray.close()
                return
        try:
            while True:
                event = events.get_nowait()
                if event == "wake":
                    launch_jarvis()
                elif event == "resume":
                    child_process = None
                    if STOP.exists():
                        exit_completely()
                    else:
                        tray.set_tooltip("JARVIS — hibernado, aguardando Hey Jarvis")
                        tray.show()
                        log("JARVIS exited; tray restored and listener resuming")
                        start_listener()
                elif event == "exit":
                    tray.close()
        except queue.Empty:
            pass

    try:
        tray = WakeTray(ICON, launch_jarvis, exit_completely, poll_events)
        log("native Win32 hibernation tray icon shown (no Qt)")
        start_listener(parent_pid)
        return tray.run()
    except Exception as exc:
        log(f"native tray failed: {type(exc).__name__}: {exc}")
        return 3
    finally:
        stop_event.set()
        if tray:
            tray.close()
        if mutex:
            try:
                mutex[0].CloseHandle(ctypes.c_void_p(mutex[1]))
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
