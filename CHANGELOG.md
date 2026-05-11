# Changelog

All notable changes to this project are documented here.

## [1.0.0] — 2026-05-10

First public release of Littlefoot programs and matching DAW controller scripts for the **ROLI Lightpad Block** (Enhanced Mixer block).

### Littlefoot (ROLI Dashboard)

- **`Enhanced Mixer Block.channel.littlefoot`** — Default **channel-strip** layout: transport row (stop / play / record / metronome), solo/mute, three main faders (mod wheel, pan, volume), and extra banks of four faders.
- **`Enhanced Mixer Block.4faders.littlefoot`** — Alternate **four-bank** fader layout with configurable row-1 button behavior and CC per column; bank 1 “main” faders plus standard fader banks.
- **`MIDI-CC-defaults.md`** — Reference for default MIDI CC assignments.

### FL Studio

- **`device_Lightpad Block_channel.py`** — Controller script aligned with the channel Littlefoot program.
- **`device_Lightpad Block_4faders.py`** — Controller script aligned with the four-fader Littlefoot program.
- **`Lightpad Block.ini`** — Device metadata for FL Studio.

### Bitwig Studio

- **`ROLI-Lightpad-Block-M.bwextension`** (**Enhanced Mixer**) — Transport, solo/mute/pan/volume on the selected track, eight Bitwig Remote controls (configurable CC base). Auto-detects **Lightpad Block** MIDI ports.
- **`ROLI-Lightpad-Block-4faders.bwextension`** (**4 Faders**) — Transport-only mapping with matching LED feedback; leaves other CCs for host MIDI mapping. Does **not** auto-detect (add manually when using the four-fader Dashboard program).

Built from `bitwig/` with `./build.zsh` (requires a local Bitwig Studio install for `bitwig.jar`). See [`bitwig/README.md`](bitwig/README.md).

### Documentation

- Root [`README.md`](README.md) — Overview of Littlefoot variants and how they pair with FL Studio and Bitwig.
