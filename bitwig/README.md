# ROLI Lightpad Block M — Bitwig extensions

Java controller extensions for the Lightpad Block M, built from one codebase.

## Variants

| Artifact | Use case | Auto-detect Lightpad USB |
|----------|----------|---------------------------|
| **`ROLI-Lightpad-Block-M.bwextension`** | **Enhanced Mixer** — matches the channel-strip style script: transport, solo/mute/pan/volume on the selected track, eight Bitwig **Remote controls** from a configurable CC base (default **116–123**). | Yes (`Lightpad Block` port prefix) |
| **`ROLI-Lightpad-Block-4faders.bwextension`** | **4 Faders** — matches the four-bank fader Littlefoot script: **only** transport (stop/play/record/metronome) and the same LED feedback as above. **Does not** capture solo/mute/pan/volume or fader CCs so slider banks can go to the DAW for MIDI mapping / learning. | No — add this controller **manually** in Bitwig |

Bitwig normally wires **one** controller script per hardware device. Because both extensions talk to the same MIDI ports, **only the Enhanced Mixer variant registers for automatic discovery**. Install both `.bwextension` files if you switch Dashboard programs; pick **ROLI Lightpad Block M (4 Faders)** from the controller list when using the four-fader layout.

## Build (macOS)

Requires Bitwig Studio (for `bitwig.jar`), Java 8+ (`javac` / `jar`), `rsync`, and zsh.

```zsh
cd bitwig
./build.zsh
```

Override Bitwig location if needed:

```zsh
BITWIG_APP_PATH="/path/to/Bitwig Studio.app" ./build.zsh
```

Outputs:

- `build/ROLI-Lightpad-Block-M.bwextension`
- `build/ROLI-Lightpad-Block-4faders.bwextension`

Install by copying the `.bwextension` files into your Bitwig user extensions folder (e.g. `~/Documents/Bitwig Studio/Extensions`) and restarting Bitwig or reloading controllers.

CC numbers for transport (and, on the Enhanced Mixer script, strip + remote base) are configurable under **Preferences → Control Change** (and **MIDI channel** under **MIDI**).

The extensions are registered with manufacturer **Roli** so they group with Bitwig’s stock Roli definitions.

## Notes (Enhanced Mixer)

- **Remote fader banks target**: **Track header remotes** vs **Selected device remotes**. Both remote pages are created at startup; switching the menu only changes which page drives the eight CCs (LED feedback follows).
- **First remote fader CC** (default 116): eight consecutive CCs map to remotes. Additional CCs are not handled by this script (see variant table for the 4-faders bundle).
- CC 1 (mod wheel) is ignored by the callback so it can map elsewhere.
- Metronome CC: high turns the click on; low off; a second high within ~550 ms toggles count-in (`preRoll` between `none` and `one_bar`). Beat flashes use the same CC (127 pulse, then restore).
- Controller API level **21**.
