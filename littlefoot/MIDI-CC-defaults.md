# Default MIDI CC layout (Littlefoot)

These are the **factory defaults** baked into the Dashboard metadata (`initStart` / fixed `value` attributes). All CC numbers are **0–127**. **MIDI channel** defaults to **1** unless you change it in ROLI Dashboard (the scripts send on channel **MIDI channel − 1** in wire format).

---

## Enhanced Mixer Block — `Enhanced Mixer Block.4faders.littlefoot`

Four touch buttons along the bottom row and **four banks** of four vertical faders (mode switches bank). Bank **1** uses the configurable **main** faders (send / pan / volume style); banks **2–4** use twelve **standard** faders intended for host MIDI mapping.

### Buttons (left → right)

Dashboard groups match the channel-strip script: **Button 1 (stop)**, **Button 2 (play)**, **Button 3 (record)**, **Button 4 (metronome)**. Each contains **Button Behavior** (Toggle / Gate / Trigger) and **MIDI CC**.

| Button | Default CC | Default behaviour (metadata) |
|--------|------------|--------------------------------|
| 1 | 102 | Toggle |
| 2 | 103 | Toggle |
| 3 | 104 | Toggle |
| 4 | 105 | Toggle |

Gate sends **127** while held and **0** on release (with script-specific LED rules). Toggle alternates between **0** and **127** each press. Trigger sends **127** then decays (see Dashboard tooltips).

### Main faders (bank 1 only — columns left → right)

| Fader | Default CC | Default curve |
|-------|------------|---------------|
| 1 | 112 | Standard or Bidirectional (per-fader Dashboard setting) |
| 2 | 113 | |
| 3 | 114 | |
| 4 | 115 | |

### Standard faders (banks 2–4 — twelve CCs, four visible per bank)

| Standard fader (script index 0–11) | Default CC |
|-----------------------------------|------------|
| 0 | 116 |
| 1 | 117 |
| 2 | 118 |
| 3 | 119 |
| 4 | 120 |
| 5 | 121 |
| 6 | 122 |
| 7 | 123 |
| 8 | 124 |
| 9 | 125 |
| 10 | 126 |
| 11 | 127 |

---

## Enhanced Mixer Block — `Enhanced Mixer Block.channel.littlefoot`

Channel-strip style: primary row has **mod wheel**, **pan**, **volume**, plus **solo** / **mute** strip buttons; four transport-style buttons; three extra banks of four faders each.

### Transport row (fixed layout in script)

| Control | Default CC | Notes |
|---------|------------|--------|
| Button 1 (stop) | 102 | Gate |
| Button 2 (play) | 103 | Toggle |
| Button 3 (record) | 104 | Toggle |
| Button 4 (metronome) | 105 | Gated latch (see script / Dashboard tooltip) |

### Channel strip

| Control | Default CC |
|---------|------------|
| Fader 1 (mod wheel) | 1 |
| Fader 2 (pan) | 112 |
| Fader 3 (volume) | 113 |
| Solo button | 106 |
| Mute button | 107 |

### Additional banks (when switched onto that bank)

| Bank | Faders (left → right, four columns) | CC range |
|------|---------------------------------------|----------|
| Bank 1 | four faders | 116–119 |
| Bank 2 | four faders | 120–123 |
| Bank 3 | four faders | 124–127 |

---

## Related Bitwig extensions

Under `bitwig/`, **`ROLI-Lightpad-Block-M.bwextension`** follows the channel-strip script (transport + strip + eight remotes from **First remote fader CC**, default **116**). **`ROLI-Lightpad-Block-4faders.bwextension`** matches the four-fader Littlefoot layout: **transport CCs only** (defaults **102–105**), leaving other CCs for host mapping. See `bitwig/README.md`.
