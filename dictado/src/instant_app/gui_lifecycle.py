"""Windows-only helpers for keeping a single Instant GUI window."""
import ctypes
import os
import time
from ctypes import wintypes


_MUTEX_NAME = "Local\\Instant.GUI"
_ERROR_ALREADY_EXISTS = 183
_SW_RESTORE = 9
_WM_CLOSE = 0x0010
_GUI_ACTION_MESSAGE = 0x8000 + 0x4A1
_ACTION_START_DAEMON = 1
_ACTION_SETUP = 2
_ACTION_DIAGNOSTICS = 3


def _user32():
    dll = ctypes.WinDLL("user32", use_last_error=True)
    dll.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
    dll.FindWindowW.restype = wintypes.HWND
    dll.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    dll.SetForegroundWindow.argtypes = (wintypes.HWND,)
    dll.SetForegroundWindow.restype = wintypes.BOOL
    dll.PostMessageW.argtypes = (
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    dll.PostMessageW.restype = wintypes.BOOL
    dll.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    dll.GetWindowThreadProcessId.restype = wintypes.DWORD
    return dll


def focus_existing_gui(request_daemon_start=False, page=None):
    """Restore the GUI and optionally request a page or daemon start."""
    if os.name != "nt":
        return False
    user32 = _user32()
    hwnd = user32.FindWindowW(None, "Instant")
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, _SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    action = None
    if request_daemon_start:
        action = _ACTION_START_DAEMON
    elif page == "setup":
        action = _ACTION_SETUP
    elif page == "diagnostics":
        action = _ACTION_DIAGNOSTICS
    if action is not None:
        user32.PostMessageW(hwnd, _GUI_ACTION_MESSAGE, action, 0)
    return True


def terminate_existing_gui(graceful_ms=1500):
    """Cierra (o termina) el panel si está abierto. True si había uno.

    Un WM_CLOSE solo no alcanza para tareas que necesitan la carpeta libre
    (desinstalador, actualización): el panel puede quedar vivo esperando
    workers. Primero se intenta el cierre limpio y, si sigue ahí, se termina
    el proceso dueño de la ventana, que es siempre nuestro.
    """
    if os.name != "nt":
        return False
    user32 = _user32()
    hwnd = user32.FindWindowW(None, "Instant")
    if not hwnd:
        return False
    close_existing_gui()
    deadline = time.monotonic() + max(0, graceful_ms) / 1000
    while time.monotonic() < deadline:
        if not user32.FindWindowW(None, "Instant"):
            return True
        time.sleep(0.1)
    hwnd = user32.FindWindowW(None, "Instant")
    if not hwnd:
        return True
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    _PROCESS_TERMINATE = 0x0001
    handle = kernel32.OpenProcess(_PROCESS_TERMINATE, False, pid.value)
    if not handle:
        return False
    try:
        return bool(kernel32.TerminateProcess(handle, 0))
    finally:
        kernel32.CloseHandle(handle)


def close_existing_gui():
    """Ask the existing Qt window to close through its normal close handler."""
    if os.name != "nt":
        return False
    user32 = _user32()
    hwnd = user32.FindWindowW(None, "Instant")
    if not hwnd:
        return False
    return bool(user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0))


def acquire_gui_mutex(request_daemon_start=False, page=None):
    """Return the owning mutex handle, or None when another GUI owns it."""
    if os.name != "nt":
        return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (
        wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        focus_existing_gui(
            request_daemon_start=request_daemon_start, page=page)
        return None
    return handle


def release_gui_mutex(handle):
    if os.name == "nt" and handle not in (None, True):
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.CloseHandle(handle)
