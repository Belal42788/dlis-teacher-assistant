"""Keeps a secret (an AI service key) in the computer's own safe instead of in a file: Windows Credential Manager, the macOS Keychain,
or the Linux Secret Service (`secret-tool`) when it is installed. Every call answers True / the value / None and never raises: when no safe
is available the caller keeps the secret in its protected file as before, so nothing breaks, it is only less safe.
Set DLIS_NO_KEYCHAIN=1 to turn this off (the tests do). DLIS_KEYCHAIN_SERVICE changes the name the entries are kept under."""
from __future__ import annotations

import os
import subprocess
import sys

_DEFAULT_SERVICE = "DLIS Teacher Assistant"


def _service() -> str:
    return os.environ.get("DLIS_KEYCHAIN_SERVICE") or _DEFAULT_SERVICE


def backend() -> str:
    """"windows", "macos", "linux" or "" (no safe on this computer, or turned off)."""
    if os.environ.get("DLIS_NO_KEYCHAIN"):
        return ""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        try:
            subprocess.run(["secret-tool", "--version"], capture_output=True, timeout=5)
            return "linux"
        except (OSError, subprocess.SubprocessError):
            return ""
    return ""


# ------------------------------------------------------------------ Windows (Credential Manager through ctypes: nothing to install)
def _win():
    import ctypes
    from ctypes import wintypes

    class CRED(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                    ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                    ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                    ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.CredWriteW.argtypes = [ctypes.POINTER(CRED), wintypes.DWORD]
    adv.CredWriteW.restype = wintypes.BOOL
    adv.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CRED))]
    adv.CredReadW.restype = wintypes.BOOL
    adv.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    adv.CredDeleteW.restype = wintypes.BOOL
    adv.CredFree.argtypes = [ctypes.c_void_p]
    return ctypes, CRED, adv


def _win_set(name: str, value: str) -> bool:
    ctypes, CRED, adv = _win()
    raw = value.encode("utf-8")
    if not raw or len(raw) > 2500:                       # Windows keeps at most 2560 bytes per entry
        return False
    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    cred = CRED(Type=1, TargetName=f"{_service()}/{name}", CredentialBlobSize=len(raw), CredentialBlob=buf, Persist=2, UserName="DLIS")
    return bool(adv.CredWriteW(ctypes.byref(cred), 0))


def _win_get(name: str) -> str | None:
    ctypes, CRED, adv = _win()
    p = ctypes.POINTER(CRED)()
    if not adv.CredReadW(f"{_service()}/{name}", 1, 0, ctypes.byref(p)):
        return None
    try:
        c = p.contents
        return ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize).decode("utf-8")
    finally:
        adv.CredFree(p)


def _win_delete(name: str) -> bool:
    _ctypes, _CRED, adv = _win()
    return bool(adv.CredDeleteW(f"{_service()}/{name}", 1, 0))


# ------------------------------------------------------------------ macOS (the `security` tool that ships with the system)
def _run(cmd: list[str], stdin: str | None = None) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None


def _mac_set(name: str, value: str) -> bool:
    r = _run(["security", "add-generic-password", "-U", "-s", _service(), "-a", name, "-w", value])
    return bool(r and r.returncode == 0)


def _mac_get(name: str) -> str | None:
    r = _run(["security", "find-generic-password", "-s", _service(), "-a", name, "-w"])
    return r.stdout.rstrip("\n") if r and r.returncode == 0 else None


def _mac_delete(name: str) -> bool:
    r = _run(["security", "delete-generic-password", "-s", _service(), "-a", name])
    return bool(r and r.returncode == 0)


# ------------------------------------------------------------------ Linux (Secret Service through secret-tool, when installed)
def _lin_set(name: str, value: str) -> bool:
    r = _run(["secret-tool", "store", "--label", f"{_service()} {name}", "service", _service(), "account", name], stdin=value)
    return bool(r and r.returncode == 0)


def _lin_get(name: str) -> str | None:
    r = _run(["secret-tool", "lookup", "service", _service(), "account", name])
    return r.stdout if r and r.returncode == 0 and r.stdout else None


def _lin_delete(name: str) -> bool:
    r = _run(["secret-tool", "clear", "service", _service(), "account", name])
    return bool(r and r.returncode == 0)


_OPS = {"windows": (_win_set, _win_get, _win_delete), "macos": (_mac_set, _mac_get, _mac_delete), "linux": (_lin_set, _lin_get, _lin_delete)}


def save(name: str, value: str) -> bool:
    """Put `value` in the safe; True only when it was written AND reads back the same (otherwise the caller must keep it itself)."""
    b = backend()
    if not b or not value:
        return False
    try:
        return _OPS[b][0](name, value) and _OPS[b][1](name) == value
    except Exception:
        return False


def load(name: str) -> str | None:
    b = backend()
    if not b:
        return None
    try:
        return _OPS[b][1](name)
    except Exception:
        return None


def delete(name: str) -> None:
    b = backend()
    if b:
        try:
            _OPS[b][2](name)
        except Exception:
            pass
