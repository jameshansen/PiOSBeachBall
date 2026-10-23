#!/usr/bin/env python3
"""Spinning beachball cursor for Raspberry Pi OS (labwc) while an app launched from the menu or desktop has no window yet.

The desktop (pcmanfm, which also runs the file manager windows) starts apps as its own children. The panel menu
starts them through GLib, which tags each app with GIO_LAUNCHED_DESKTOP_FILE_PID=<its pid> and orphans it. When
either appears, a transparent overlay turns the cursor into the beachball until a new window maps, all of the
app's processes exit, the user clicks or TIMEOUT passes.

Run with --selftest to launch `sleep 1` both ways and check the beachball comes and goes with it.
"""
import glob
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk, GtkLayerShell  # noqa: E402

LAUNCHERS = {"pcmanfm"}  # every child is an app launch
HERE = os.path.dirname(os.path.abspath(__file__))
FRAMES = sorted(glob.glob(os.path.join(HERE, "frames", "*.png")) or glob.glob(os.path.join(HERE, "blender", "frames", "*.png")))
SIZE = int(os.environ.get("XCURSOR_SIZE") or 24) * 4 // 3  # a touch larger than the arrow
FRAME_MS = 33  # 36 frames, about 1.2 seconds per turn
POLL_MS = 200
SHOW_DELAY = 0.3  # seconds; apps that open faster never show the beachball
TIMEOUT = 180  # seconds; modded Minecraft takes over a minute on a Pi 400


def stat(pid):
    """(name, state, parent pid) of a process, or None once it is gone."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            head, tail = f.read().rsplit(")", 1)
    except OSError:
        return None
    state, ppid = tail.split()[:2]
    return head.split("(", 1)[1], state, int(ppid)


def launch_root(pid):
    """The pid GLib recorded when it launched this process's app, or None."""
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            env = f.read().split(b"\0")
    except OSError:
        return None
    for kv in env:
        if kv.startswith(b"GIO_LAUNCHED_DESKTOP_FILE_PID="):
            return int(kv.split(b"=", 1)[1])
    return None


def alive(pid):
    st = stat(pid)
    return bool(st) and st[1] != "Z"


def all_pids():
    return {int(p) for p in os.listdir("/proc") if p.isdigit()}


class Toplevels:
    """Calls on_new() whenever a window maps. A bare-bones Wayland client for zwlr_foreign_toplevel_manager_v1,
    the protocol the panel's taskbar uses, so no extra packages are needed."""

    def __init__(self, on_new):
        self.on_new, self.buf, self.manager = on_new, b"", None
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(os.path.join(os.environ["XDG_RUNTIME_DIR"], os.environ["WAYLAND_DISPLAY"]))
        self.send(1, 1, 2)  # wl_display.get_registry(new_id 2)
        GLib.io_add_watch(self.sock.fileno(), GLib.IO_IN | GLib.IO_HUP, self.read)

    def send(self, obj, opcode, *args):
        body = b"".join(a if isinstance(a, bytes) else struct.pack("<I", a) for a in args)
        self.sock.sendall(struct.pack("<II", obj, (8 + len(body)) << 16 | opcode) + body)

    def read(self, *_):
        data = self.sock.recv(65536)
        if not data:
            Gtk.main_quit()  # compositor gone, session over
            return False
        self.buf += data
        while len(self.buf) >= 8:
            obj, word = struct.unpack_from("<II", self.buf)
            if len(self.buf) < word >> 16:
                break
            self.event(obj, word & 0xFFFF, self.buf[8:word >> 16])
            self.buf = self.buf[word >> 16:]
        return True

    def event(self, obj, opcode, args):
        if obj == 2 and opcode == 0:  # wl_registry.global(name, interface, version)
            name, n = struct.unpack_from("<II", args)
            end = 8 + (n + 3) // 4 * 4
            if args[8:8 + n - 1] == b"zwlr_foreign_toplevel_manager_v1":
                self.manager = 3
                self.send(2, 0, name, args[4:end], min(struct.unpack_from("<I", args, end)[0], 3), 3)  # bind
        elif obj == self.manager and opcode == 0:  # toplevel(handle)
            self.on_new()
        elif obj >= 0xFF000000 and opcode == 6:  # handle.closed
            self.send(obj, 7)  # handle.destroy


class BeachBall:
    def __init__(self):
        disp = Gdk.Display.get_default()
        self.cursors = [Gdk.Cursor.new_from_pixbuf(disp, GdkPixbuf.Pixbuf.new_from_file_at_size(f, SIZE, SIZE), SIZE // 2, SIZE // 2)
                        for f in FRAMES]
        css = Gtk.CssProvider()
        css.load_from_data(b"window { background: transparent; }")
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.launches = {}  # root pid -> (time seen, pids belonging to the app)
        self.seen, self.fresh = all_pids(), set()  # anything already running is not a launch
        self.wins, self.frame, self.timer = [], 0, None
        Toplevels(self.done)
        GLib.timeout_add(POLL_MS, self.poll)

    def scan(self):
        """ponytail: a desktop-launched app that orphans its own helper before the next poll loses track of it;
        match on inherited DESKTOP_STARTUP_ID too if an app needs it."""
        pids = all_pids()
        # Recheck last round's newcomers: a fresh fork carries its parent's environment until it execs.
        for pid in sorted((pids - self.seen) | (self.fresh & pids)):  # parents before children
            st = stat(pid)
            if not st:
                continue
            root, parent = launch_root(pid), stat(st[2])
            if pid not in self.launches and (root == pid or parent and parent[0] in LAUNCHERS):
                self.launches[pid] = (time.monotonic(), {pid})
                print("launch", pid, flush=True)
            else:
                for r, (_, members) in self.launches.items():
                    if st[2] in members or root == r:
                        members.add(pid)
        self.fresh, self.seen = pids - self.seen, pids

    def poll(self):
        self.scan()
        now = time.monotonic()
        for root, (t, pids) in list(self.launches.items()):
            st = stat(root)
            if st and "thumbnail" in st[0]:  # file manager thumbnailers are not apps
                del self.launches[root]
            elif now - t > TIMEOUT or not any(map(alive, pids)):
                print("ended", root, st and st[0], "timeout" if now - t > TIMEOUT else "exited", flush=True)
                del self.launches[root]
        if not self.launches:
            self.hide()
        elif not self.wins and now - min(t for t, _ in self.launches.values()) >= SHOW_DELAY:
            self.show()
        return True

    def done(self, *_):
        """A window mapped or the user clicked. ponytail: ends every pending launch, not only the one that opened."""
        if self.launches:
            print("window or click, done", flush=True)
        self.launches.clear()
        self.hide()
        return True

    def show(self):
        disp = Gdk.Display.get_default()
        for i in range(disp.get_n_monitors()):
            w = Gtk.Window()
            GtkLayerShell.init_for_window(w)
            GtkLayerShell.set_namespace(w, "pibeachball")
            GtkLayerShell.set_layer(w, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_monitor(w, disp.get_monitor(i))
            GtkLayerShell.set_exclusive_zone(w, -1)
            for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
                GtkLayerShell.set_anchor(w, edge, True)
            w.set_visual(w.get_screen().get_rgba_visual())
            w.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.SCROLL_MASK)
            w.connect("button-press-event", self.done)
            w.connect("scroll-event", self.done)
            w.show()
            self.wins.append(w)
        self.tick()
        self.timer = GLib.timeout_add(FRAME_MS, self.tick)

    def tick(self):
        self.frame = (self.frame + 1) % len(self.cursors)
        for w in self.wins:
            w.get_window().set_cursor(self.cursors[self.frame])
        return True

    def hide(self):
        if self.wins:
            GLib.source_remove(self.timer)
            for w in self.wins:
                w.destroy()
            self.wins = []


def selftest():
    bb = BeachBall()

    def run(launch):
        shown = []
        launch()
        GLib.timeout_add(250, lambda: shown.append(bool(bb.wins)) or len(shown) < 10 or Gtk.main_quit())
        Gtk.main()
        assert True in shown and not shown[-1], shown

    with tempfile.NamedTemporaryFile("w", suffix=".desktop") as f:
        f.write("[Desktop Entry]\nType=Application\nName=selftest\nExec=sleep 1\n")
        f.flush()
        run(lambda: Gio.DesktopAppInfo.new_from_filename(f.name).launch([], None))  # the menu's way
    LAUNCHERS.add(stat(os.getpid())[0])
    run(lambda: subprocess.Popen(["sleep", "1"]))  # the desktop's way
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        selftest()
    else:
        BeachBall()
        Gtk.main()
