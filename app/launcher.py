"""Starts the app: local server + a window. Falls back to the normal browser if no window is available."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import threading
import time
import webbrowser

from .core import paths

paths.startup_mark("launcher loaded")

IDLE_SECONDS = 45  # browser mode: quit when the page has not pinged for this long


def _wait_for_browser_close(server) -> None:
    print(f"\n  {paths.APP_NAME} is running at {server.url}")
    print("  Close the browser tab to quit (or press Ctrl+C).\n")
    started = time.time()
    try:
        while True:
            time.sleep(1)
            idle = time.time() - server.last_ping
            if server.seen_ping and idle > IDLE_SECONDS:
                return
            if not server.seen_ping and time.time() - started > 120:
                return
    except KeyboardInterrupt:
        return


_LOCK_PORT = 47651  # a fixed local port: only one copy of the app runs, so reminders never pop up twice


def _build_id() -> str:
    """Which build is this? A new .exe built from the same version number must still count as a different copy."""
    try:
        if getattr(sys, "frozen", False):
            return f"{paths.VERSION}-{int(os.path.getmtime(sys.executable))}"
    except OSError:
        pass
    return paths.VERSION


def _single_instance(on_show, on_quit=None) -> bool:
    """True if we are the first copy. If another copy of the SAME build is running, ask it to show its window and stop.
    If it is an older build (still sitting in the tray), ask it to quit and take over."""
    import socket
    import threading

    mine = _build_id().encode()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def bind() -> bool:
        try:
            srv.bind(("127.0.0.1", _LOCK_PORT))
            srv.listen(4)
            return True
        except OSError:
            return False

    if not bind():
        try:
            with socket.create_connection(("127.0.0.1", _LOCK_PORT), timeout=2) as c:
                c.sendall(b"show " + mine)
                c.settimeout(3)
                reply = c.recv(16)
        except OSError:
            return True  # something else owns the port; just run
        if reply != b"old":
            return False  # the same build is already open; it was asked to show itself
        for _ in range(30):  # the older copy is closing: wait for the port, then take over
            time.sleep(0.2)
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if bind():
                break
        else:
            return True

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
                conn.settimeout(1)
                msg = conn.recv(64)
                if msg == b"show" or msg == b"show " + mine:
                    on_show()
                    conn.sendall(b"same")
                elif msg.startswith(b"show ") and on_quit:
                    conn.sendall(b"old")  # a different build wants to run: leave
                    conn.close()
                    on_quit()
                    continue
                conn.close()
            except OSError:
                time.sleep(0.5)  # never spin the CPU if the socket breaks

    threading.Thread(target=loop, daemon=True).start()
    return True


def _set_autostart(on: bool) -> None:
    """Windows: start with the computer (hidden, near the clock)."""
    import winreg

    name = "DLIS Teacher Assistant"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, f'"{sys.executable}" --background')
        else:
            try:
                winreg.DeleteValue(k, name)
            except FileNotFoundError:
                pass


def _tray_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import PIL  # noqa: F401
        import pystray  # noqa: F401
        return True
    except Exception:
        return False



def _keep_taskbar_visible(window) -> None:
    """Windows: a window without a system title bar covers the whole screen when maximized, including the taskbar.
    Tell it to stay inside the working area instead."""
    if sys.platform != "win32":
        return
    try:
        from System import Action
        from System.Windows.Forms import Screen

        form = window.native

        def _set():
            form.MaximizedBounds = Screen.FromControl(form).WorkingArea

        form.Invoke(Action(_set))
    except Exception:
        pass  # not critical; --native-titlebar always respects the taskbar


def _set_window_icon(window) -> None:
    """Windows: the taskbar and the window corner show the school logo, not the Python icon."""
    if sys.platform != "win32":
        return
    try:
        from System import Action
        from System.Drawing import Icon

        ico = paths.resources_dir() / "icon.ico"
        form = window.native
        form.Invoke(Action(lambda: setattr(form, "Icon", Icon(str(ico)))))
    except Exception:
        import traceback
        paths.log_error("could not set the window icon:\n" + traceback.format_exc())


def _enable_taskbar_minimize(window) -> None:
    """Windows: a window with no system title bar lacks the 'minimize' style, so clicking its taskbar button while it is
    showing does nothing. Give it the style (invisible: there is no title bar to draw it on)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from System import Action

        form = window.native

        def _set():
            hwnd = ctypes.c_void_p(int(form.Handle.ToInt64()))
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
            user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
            style = user32.GetWindowLongW(hwnd, -16)  # GWL_STYLE
            user32.SetWindowLongW(hwnd, -16, style | 0x00020000 | 0x00080000)  # WS_MINIMIZEBOX | WS_SYSMENU
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)  # keep size/position, refresh the frame

        form.Invoke(Action(_set))
    except Exception:
        paths.log_error("could not enable taskbar minimize")


def _report_crash() -> None:
    """A windowed .exe has no console, so write what went wrong to a file the teacher can send us."""
    import traceback

    text = traceback.format_exc()
    try:
        log = paths.app_support_dir() / "error.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(text, encoding="utf-8")
        where = str(log)
    except OSError:
        where = "(could not write the log file)"
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, f"The program could not start.\n\nDetails were saved here:\n{where}\n\n{text[-600:]}",
                                             "DLIS Teacher Assistant", 0x10)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":  # its own taskbar identity, so the taskbar shows our icon and not python's
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DLIS.TeacherAssistant")
        except Exception:
            pass
    try:
        return _main(argv)
    except SystemExit:
        raise
    except BaseException:
        _report_crash()
        return 1


def _selftest(server, out_file: str) -> int:
    """The built program (PyInstaller) can miss a library or a data file without any error at build time. This opens each
    part the teacher would use, so the build on Windows/Mac shows the problem instead of the teacher."""
    import importlib
    import json
    import urllib.request

    problems: list[str] = []
    for mod in ("pydantic", "openpyxl", "docx", "pptx", "PIL", "pypdfium2", "certifi"):
        try:
            importlib.import_module(mod)
        except Exception as e:
            problems.append(f"import {mod}: {e}")
    if sys.platform == "win32":
        try:
            importlib.import_module("pystray._win32")
        except Exception as e:
            problems.append(f"import pystray._win32: {e}")
    if sys.platform in ("win32", "darwin"):   # on Linux the window library is optional
        try:
            import webview  # noqa: F401
        except Exception as e:
            problems.append(f"import webview: {e}")
    web = paths.web_dir()
    for rel in ("index.html", "css/style.css", "js/main.js", "js/i18n.js", "fonts/arabic.ttf"):
        if not (web / rel).is_file():
            problems.append(f"missing web file {rel}")
    res = paths.resources_dir()
    for name in ("Lesson_Plan_Temp.docx", "Quiz_Template_v2.docx", "Grading_Sheet_Template.docx", "Revision_Cover_Template.docx",
                 "Trimester_Plan_Template.docx", "ai_providers.json", "ai_prompts.json", "bell_schedule.json"):
        if not (res / name).is_file():
            problems.append(f"missing resource {name}")
    try:
        with urllib.request.urlopen(server.url, timeout=10) as r:
            if r.status != 200 or b"<html" not in r.read(4000).lower():
                problems.append("home page did not load")
        with urllib.request.urlopen(server.url.rstrip("/") + "/js/main.js", timeout=10) as r:
            if r.status != 200:
                problems.append("main.js did not load")
    except Exception as e:
        problems.append(f"server: {e}")
    Path(out_file).write_text(json.dumps({"ok": not problems, "problems": problems, "platform": sys.platform}, indent=1), encoding="utf-8")
    return 0 if not problems else 1


def _native_beep() -> None:
    """The computer's own beep: a minimised web page is not allowed to make sound."""
    try:
        if sys.platform == "win32":
            import winsound
            for _ in range(3):
                winsound.Beep(880, 200)
                time.sleep(0.08)
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], timeout=5)
        else:
            print("\a", end="", flush=True)
    except Exception:
        pass


def _drag_window(window) -> None:
    """Move the window while the mouse button is held (our own title bar). Windows only."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        hwnd = ctypes.c_void_p(int(window.native.Handle.ToInt64()))
        pt, rc = wintypes.POINT(), wintypes.RECT()
        user32.GetCursorPos(ctypes.byref(pt)); user32.GetWindowRect(hwnd, ctypes.byref(rc))
        if user32.IsZoomed(hwnd):  # dragging a maximised window brings it back to its normal size under the mouse
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.GetWindowRect(hwnd, ctypes.byref(rc))
            w1 = rc.right - rc.left
            user32.SetWindowPos(hwnd, None, pt.x - w1 // 2, pt.y - 15, 0, 0, 0x0001 | 0x0004 | 0x0010)
            user32.GetWindowRect(hwnd, ctypes.byref(rc))
        ox, oy, wx, wy = pt.x, pt.y, rc.left, rc.top
        end = time.time() + 120
        while user32.GetAsyncKeyState(0x01) & 0x8000 and time.time() < end:  # VK_LBUTTON
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetWindowPos(hwnd, None, wx + pt.x - ox, wy + pt.y - oy, 0, 0, 0x0001 | 0x0004 | 0x0010)  # no size, no z-order, no activate
            time.sleep(0.008)
        # let go at the very top of the screen = maximise (like every Windows program)
        user32.GetCursorPos(ctypes.byref(pt))
        top = 0
        try:
            class MI(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
            user32.MonitorFromPoint.restype = ctypes.c_void_p
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            mi = MI(); mi.cbSize = ctypes.sizeof(MI)
            if user32.GetMonitorInfoW(ctypes.c_void_p(user32.MonitorFromPoint(pt, 2)), ctypes.byref(mi)):
                top = mi.rcMonitor.top
        except Exception:
            top = 0
        if pt.y <= top + 4:
            window.maximize()
    except Exception:
        import traceback
        paths.log_error("could not move the window:\n" + traceback.format_exc())


def _run_app_window(server, args) -> int:
    """The app window (pywebview) with the tray icon, reminders ringing and the window controls. Raises if there is no web view
    on this computer, and the caller then falls back to the browser."""
    import webview  # pywebview: a real app window, no browser bars

    frameless = sys.platform == "win32" and args.custom_titlebar and not args.native_titlebar  # the normal title bar gives Windows 11 snap layouts (hover on maximize, Win+Z)
    svc = server.service
    state = {"tray": None, "quitting": False, "hidden": False}
    holder: dict = {}

    ring_stop = threading.Event()

    def start_ring(seconds):
        ring_stop.set()          # one ring at a time
        time.sleep(0.05)
        ring_stop.clear()

        def run():
            end = time.time() + (seconds if seconds > 0 else 3600)
            while not ring_stop.is_set() and time.time() < end:
                _native_beep()
                ring_stop.wait(1.8)
        threading.Thread(target=run, daemon=True).start()

    def show_window():
        w = holder.get("window")
        if w:
            try:
                w.show()
                # only un-minimize: restore() on a maximized window would shrink it back to its small size
                minimized = True
                if sys.platform == "win32":
                    try:
                        minimized = int(w.native.WindowState) == 1  # FormWindowState.Minimized
                    except Exception:
                        minimized = True
                if minimized or state["hidden"]:
                    w.restore()
                state["hidden"] = False
            except Exception:
                pass

    hooks: dict = {}
    if not _single_instance(show_window, lambda: hooks.get("quit") and hooks["quit"]()):
        server.shutdown()
        return 0

    ar = paths.read_prefs().get("language") == "ar"

    def start_tray():
        if state["tray"] or not _tray_available():
            return
        import pystray
        from PIL import Image

        menu = pystray.Menu(
            pystray.MenuItem("فتح البرنامج" if ar else "Open", lambda *a: show_window(), default=True),
            pystray.MenuItem("إغلاق تمامًا" if ar else "Quit", lambda *a: quit_app()))
        icon = pystray.Icon("DLIS", Image.open(paths.resources_dir() / "icon.png"), paths.APP_NAME, menu)
        icon.run_detached()
        state["tray"] = icon

    def stop_tray():
        if state["tray"]:
            try:
                state["tray"].stop()
            except Exception:
                pass
            state["tray"] = None

    def quit_app():
        state["quitting"] = True
        stop_tray()
        try:
            holder["window"].destroy()
        except Exception:
            pass

    hooks["quit"] = quit_app

    def close_clicked():
        if state["tray"] and not state["quitting"]:
            holder["window"].hide()
            state["hidden"] = True
        else:
            quit_app()

    class WindowControls:  # called from the page
        def minimize(self):
            holder["window"].minimize()

        def toggle_maximize(self):
            _keep_taskbar_visible(holder["window"])
            state_max = getattr(self, "_max", False)
            (holder["window"].restore if state_max else holder["window"].maximize)()
            self._max = not state_max

        def start_drag(self):
            """Move the window while the mouse button is held (our own title bar; works on every Windows version)."""
            _drag_window(holder["window"])

        def close(self):
            close_clicked()

        def reminder_stop(self):
            ring_stop.set()

        def reminder_alert(self, text="", sound=True, seconds=60):
            """A reminder is due: bring the window up, ring (played by the computer itself, because a minimised
            web page is not allowed to make sound) and show a balloon if it was hidden."""
            was_hidden = state["hidden"]
            if sound:
                start_ring(int(seconds or 0))
            show_window()
            if was_hidden and state["tray"]:
                try:
                    state["tray"].notify(str(text)[:200], paths.APP_NAME)
                except Exception:
                    pass

    # what this computer can do in the background
    svc.background_support = {"tray": _tray_available(), "autostart": sys.platform == "win32" and bool(getattr(sys, "frozen", False))}

    def apply_background(cfg):
        if cfg.get("keep_running"):
            start_tray()
        else:
            stop_tray()
            show_window()
        if svc.background_support["autostart"]:
            try:
                _set_autostart(bool(cfg.get("autostart")))
            except Exception:
                pass

    svc.apply_background = apply_background
    saved_bg = paths.read_prefs().get("background") or {}
    if saved_bg.get("keep_running"):
        start_tray()
    start_hidden = bool(args.background and state["tray"])

    paths.startup_mark("creating the window")
    window = webview.create_window(paths.APP_NAME, server.url, width=1320, height=860, min_size=(960, 640), hidden=start_hidden,
                                   frameless=frameless, easy_drag=False, js_api=WindowControls())
    holder["window"] = window
    state["hidden"] = start_hidden
    svc.frameless = frameless

    def on_closing():  # the system close button / Alt+F4: hide near the clock instead of quitting
        if state["tray"] and not state["quitting"]:
            window.hide()
            state["hidden"] = True
            return False
        return None

    window.events.closing += on_closing
    window.events.shown += lambda: (paths.startup_mark("window shown"), _keep_taskbar_visible(window), _enable_taskbar_minimize(window), _set_window_icon(window))

    def native_folder_dialog(start: str = ""):
        kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        start = start if start and Path(start).is_dir() else str(Path.home())
        res = window.create_file_dialog(kind, directory=start)
        return res[0] if res else ""

    svc.native_folder_dialog = native_folder_dialog

    def keep_ticking():  # a hidden window may slow its timers down; nudge the reminder check
        while True:
            time.sleep(20)
            if state["hidden"]:
                try:
                    window.evaluate_js("window.__dlisTick && window.__dlisTick()")
                except Exception:
                    pass


    threading.Thread(target=keep_ticking, daemon=True).start()
    webview.start()
    stop_tray()
    server.shutdown()
    return 0


def _main(argv: list[str] | None = None) -> int:
    for name in ("stdout", "stderr"):  # a windowed .exe has none; anything that prints would crash
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    ap = argparse.ArgumentParser(prog="dlis")
    ap.add_argument("--browser", action="store_true", help="open in the normal browser instead of an app window")
    ap.add_argument("--no-window", action="store_true", help="only run the server (for tests)")
    ap.add_argument("--native-titlebar", action="store_true", help="use the normal Windows title bar (this is the default now)")
    ap.add_argument("--custom-titlebar", action="store_true", help="use our own slim title bar (Windows snap layouts do not work with it)")
    ap.add_argument("--background", action="store_true", help="start hidden near the clock (used when Windows starts)")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--selftest", metavar="FILE", help="check that the packaged program is complete, write the result to FILE and quit (used by the build)")
    args = ap.parse_args(argv)

    # Loading the program's own files and the window library are both slow on Windows (every file is scanned): do them at the same time.
    loaded: dict = {}

    def load_app():
        from .server.http import AppServer
        loaded["AppServer"] = AppServer
        paths.startup_mark("program files loaded")

    loader = threading.Thread(target=load_app, daemon=True)
    loader.start()
    if not (args.browser or args.no_window or args.selftest) and sys.platform in ("win32", "darwin"):
        try:
            import webview  # noqa: F401  (loaded here, used when the window is made)
            paths.startup_mark("window library loaded")
        except Exception:
            pass   # _run_app_window reports it and falls back to the browser
    loader.join()
    server = loaded["AppServer"](port=args.port)
    server.start_in_thread()
    paths.startup_mark("server ready")
    if args.selftest:
        return _selftest(server, args.selftest)

    if args.no_window:
        print(server.url, flush=True)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    if not args.browser:
        try:
            return _run_app_window(server, args)
        except Exception as e:  # not installed, or no web view on this computer
            import traceback
            paths.log_error("App window could not start, so the browser was used instead:\n" + traceback.format_exc())
            try:
                print(f"(No app window available: {e}. Opening your browser instead.)")
            except Exception:
                pass

    webbrowser.open(server.url)
    _wait_for_browser_close(server)
    server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
