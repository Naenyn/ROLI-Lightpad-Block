# ROLI-Lightpad-Block

Littlefoot programs for the **ROLI Lightpad Block** (Enhanced Mixer layout) plus matching **DAW controller scripts** for **FL Studio** and **Bitwig Studio**.

---

## Littlefoot (ROLI Dashboard)

Two programs ship under `littlefoot/`:

### Channel strip — default (`Enhanced Mixer Block.channel.littlefoot`)

Treat this as the **default** layout when you want a **single-channel strip** on the primary bank: four transport-style buttons on row 1 (stop / play / record / metronome with fixed behaviors in code), **solo** and **mute** strip controls, three main faders (mod wheel, pan, volume), and additional banks of four faders each. Transport CCs and many other assignments are exposed in Dashboard.

Default MIDI CC layout is summarized in [`littlefoot/MIDI-CC-defaults.md`](littlefoot/MIDI-CC-defaults.md).

### Four-fader banks — alternate (`Enhanced Mixer Block.4faders.littlefoot`)

An **alternate** layout: **four banks** of four vertical faders (bank 1 uses configurable “main” fader curves; banks 2–4 use twelve standard faders). Row 1 has four **transport-intended** buttons; each column has its own **Button Behavior** (Toggle / Gate / Trigger) and **MIDI CC** in Dashboard. Mode switches bank.

Use this program when you want all banks to behave like generic MIDI fader banks rather than the dedicated channel-strip wiring of the channel script.

---

## DAW controller scripts

Pair the Dashboard program you load on the block with the matching script in your DAW so CC mappings line up.

| DAW | Channel-strip Littlefoot | Four-fader Littlefoot |
|-----|--------------------------|------------------------|
| **FL Studio** | [`fl-studio/Lightpad Block/device_Lightpad Block_channel.py`](fl-studio/Lightpad%20Block/device_Lightpad%20Block_channel.py) | [`fl-studio/Lightpad Block/device_Lightpad Block_4faders.py`](fl-studio/Lightpad%20Block/device_Lightpad%20Block_4faders.py) |
| **Bitwig Studio** | Install **`ROLI-Lightpad-Block-M.bwextension`** (Enhanced Mixer) — see [`bitwig/README.md`](bitwig/README.md) | Install **`ROLI-Lightpad-Block-4faders.bwextension`** — same doc |

Bitwig builds both `.bwextension` bundles from one Java codebase (`bitwig/`). The Enhanced Mixer extension auto-detects **Lightpad Block** MIDI ports; the four-fader variant does not auto-install (add it manually when you use the four-fader Littlefoot program). Details: [`bitwig/README.md`](bitwig/README.md).

For FL Studio, follow Image-Line’s usual MIDI controller script installation layout (project/device folder containing the `.py` files and `Lightpad Block.ini`).
