# PiOSBeachBall

A spinning beachball cursor for Raspberry Pi OS. When an app started from the menu or a desktop icon is still loading and has no window yet, the cursor becomes a spinning beachball until the window appears or the app exits.

![beachball](blender/frames/beachball_00.png)

Tested on Raspberry Pi OS Trixie with the standard labwc (Wayland) desktop on a Pi 400 and a Pi 500. The X11 session is not supported.

## Install

On the Pi, in a terminal:

```bash
git clone https://github.com/jameshansen/PiOSBeachBall.git
cd PiOSBeachBall
./install.sh
```

The installer adds `gir1.2-gtklayershell-0.1` with `sudo apt` if it is missing, copies the program and frames to `~/.local/share/pibeachball`, adds it to autostart and starts it straight away.

## Uninstall

```bash
./install.sh --uninstall
```

## How it works

`pibeachball.py` is a small Python daemon with no dependencies beyond what Raspberry Pi OS already ships, plus the layer-shell bindings.

- Apps started from desktop icons (and from file manager windows) are children of `pcmanfm`. Apps started from the menu are launched through GLib, which tags them with `GIO_LAUNCHED_DESKTOP_FILE_PID`. The daemon polls `/proc` five times a second for either.
- If the app has no window after 0.3 seconds, a transparent overlay covers each screen and sets the cursor to the rendered beachball frames.
- New windows are picked up through the `wlr-foreign-toplevel` Wayland protocol, the same one the taskbar uses. The beachball goes away when a new window maps, when every process belonging to the app has exited, when you click, or after three minutes.

A click while the beachball is showing dismisses it and does not reach the window underneath.

Idle cost is about half a percent of one core on a Pi 400.

## Tuning

The constants at the top of `pibeachball.py` set the cursor size (`SIZE`), animation speed (`FRAME_MS`), how long an app gets before the beachball appears (`SHOW_DELAY`) and the safety cut-off (`TIMEOUT`). Re-run `./install.sh` after editing.

## Checking it

```bash
python3 pibeachball.py --selftest
```

This launches `sleep 1` the way the menu does and the way the desktop does, and checks the beachball appears and clears for each.

To watch what the daemon detects, stop the autostarted copy and run it in a terminal:

```bash
pkill -f pibeachball.py; python3 ~/.local/share/pibeachball/pibeachball.py
```

## The beachball

`blender/make_beachball.py` builds the model and renders 36 frames at 128 px into `blender/frames`, one full clockwise turn in 10 degree steps, so the spin loops seamlessly at about 1.2 seconds per turn. `blender/beachball.blend` holds the scene. To re-render:

```bash
blender -b -P blender/make_beachball.py
```
