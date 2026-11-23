import ctypes
import os
import unittest

from wake_daemon import task_worker_mutex_exists


@unittest.skipUnless(os.name == "nt", "Windows named mutex behavior")
class WorkerMutexRecoveryTests(unittest.TestCase):
    def test_stale_pid_marker_can_be_distinguished_from_live_worker(self):
        if task_worker_mutex_exists():
            self.skipTest("a real task worker currently owns the mutex")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p
        ]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(
            None, False, r"Global\JarvisTaskWorker"
        )
        self.assertTrue(handle)
        try:
            self.assertTrue(task_worker_mutex_exists())
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        self.assertFalse(task_worker_mutex_exists())


if __name__ == "__main__":
    unittest.main()
