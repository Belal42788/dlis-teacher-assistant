"""The tests never use the real internet, so they give the same answer on your computer, on GitHub and anywhere else.
Any attempt to reach a name that is not this computer fails exactly like "no internet" (the app handles that quietly).
`install()` is called at the top of each test file; the attempts are kept in ATTEMPTS so a test can check what the app tried to reach."""
import os
import socket
import traceback

ATTEMPTS: list[str] = []
_LOCAL = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}
_done = False


def _host(addr) -> str:
    return str(addr[0]) if isinstance(addr, (tuple, list)) and addr else str(addr)


def _where() -> str:
    for f in reversed(traceback.extract_stack()):
        if f.filename.replace("\\", "/").find("/tests/") >= 0 and not f.filename.endswith("nonet.py"):
            return f"{f.filename.replace(chr(92), '/').split('/tests/')[-1]}:{f.lineno} {f.name}"
    return "?"


def install() -> None:
    global _done
    if _done:
        return
    _done = True
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):   # a proxy on this computer would answer instead of the internet
        os.environ.pop(k, None)
    real_gai, real_connect, real_connect_ex = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex

    def gai(host, *a, **k):
        if _host(host) not in _LOCAL:
            ATTEMPTS.append(f"{_host(host)} from {_where()}")
            raise socket.gaierror(socket.EAI_NONAME, "no internet in tests")
        return real_gai(host, *a, **k)

    def connect(self, addr):
        if getattr(self, "family", None) in (socket.AF_INET, socket.AF_INET6) and _host(addr) not in _LOCAL:
            ATTEMPTS.append(f"{_host(addr)} from {_where()}")
            raise OSError("no internet in tests")
        return real_connect(self, addr)

    def connect_ex(self, addr):
        if getattr(self, "family", None) in (socket.AF_INET, socket.AF_INET6) and _host(addr) not in _LOCAL:
            ATTEMPTS.append(f"{_host(addr)} from {_where()}")
            return 111
        return real_connect_ex(self, addr)

    socket.getaddrinfo = gai
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
