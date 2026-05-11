# name=ROLI Lightpad Block M (Channel strip)
# supportedDevices=Lightpad Block
# Channel strip: CC1 pass-through; CC112 pan, CC113 volume; CC106 solo / CC107 mute
# (127=on, LED_DIM=off). Generic faders CC116–127 follow tracks from selected strip.
# CC105 metronome: normal toggle — first press 127 (on), next press 0 (off). Not gated (unlike BTN_STOP).
# Double “on” edge within METRO_DOUBLE_127_PRECOUN_SEC (127 … 0 … 127) toggles FL count-in (FPT_CountDown).
# FL toolbar sync: steady on=64, off=0; beat flash on CC105 uses 127 only.
# Edits for this layout go in this file only — do not mirror them to device_Lightpad Block_4faders.py unless asked.

import mixer
import channels
import transport
import midi
import ui
import device
import time

DEBUG = True
FADER_SYNC_DEBUG = True

# Hardware / transport constants
BTN_STOP = 102
BTN_PLAY = 103
BTN_RECORD = 104
BTN_METRO = 105
BTN_SOLO = 106
BTN_MUTE = 107

FADERS = {
    113: {"type": "volume", "name": "volume"},
    112: {"type": "pan", "name": "pan"},
    BTN_SOLO: {"type": "solo", "name": "solo"},
    BTN_MUTE: {"type": "mute", "name": "mute"},
}

for i, cc in enumerate(range(116, 128), start=1):
    FADERS[cc] = {"type": "generic", "name": f"fader{i}", "offset": i - 1}

# CCs we care about for debug (transport only; skip fader spam)
DEBUG_CCS = (BTN_STOP, BTN_PLAY, BTN_RECORD, BTN_METRO, BTN_SOLO, BTN_MUTE)

PULSE_DURATION = 0.12
# Play/record idle: Lightpad treats 0 or 64 as dim “off”; we use 64 only (never LED fully off).
LED_DIM = 64
# Metronome CC 105: steady on=64, off=0; 127 = beat flash.
METRO_LED_OFF = 0
METRO_LED_STEADY_ON = 64
METRO_LED_FLASH = 127
# Two CC105=127 edges within this time (with a 0 between on a toggle pad) = toggle count-in / precount.
METRO_DOUBLE_127_PRECOUN_SEC = 0.55
RECORD_HOLD_RESEND_INTERVAL = 0.05
PRIMARY_FADER_SEND_INTERVAL = 0.03

# Track lookup
lastMixerTrackSeen = -1
lastChannelSeen = -1
currentPrimaryTargetTrack = -1
lastPrimarySyncMixerTrack = -1
lastPrimarySyncChannel = -1
lastPrimarySyncFxTrack = -1
lastPrimarySyncTargetTrack = -1
lastPrimaryFaderSignature = None
pendingPrimaryFaderWrites = []
pendingPrimaryFaderNextSendAt = 0.0

# User interaction / debounce
isUserControlling = False
lastUserInputTime = 0
USER_TIMEOUT = 0.1

precountEnabled = False
metroEnabled = False
# Time of last CC105=127 (for double-127 → count-in); not cleared on CC105=0 so 127→0→127 can pair.
metroLast127EdgeTime = 0.0

# LED state caches
lastValues = {}
metroBrightUntil = 0
metroIsBright = False

recordBrightUntil = 0
recordIsBright = False

recordState = -1
metroState = -1
playState = -1
stopState = -1

# Count-in / record flow
countInSessionActive = False
recordArmed = False
countInStartTime = 0.0
countInBeatLength = 0.5   # 60/120 BPM
countInPhase = 0          # 0..4 (four quarter-note flashes)
countInNextFlashAt = 0.0
countInJustFinishedUntil = 0.0
recordSolidHoldUntil = 0.0
recordSolidAt = 0.0
waitingForRecordingStart = False
recordStartedAtBar1 = False  # set by OnUpdateBeatIndicator when pos >= 1.0
recordSolidNotBefore = 0.0
RECORD_DIM_MIN_BEATS = 1.0  # stay dim this many beats after 4th beat before allowing solid
RECORD_WAIT_TIMEOUT = 5.0   # longer than count-in (4 beats); only fallback if bar 1 never seen

# Debug / hold state
_lastRecording = None
_lastPlaying = None
_lastRecordHoldSend = 0.0

def getBPM():
    """Return project BPM; beat length in seconds = 60/getBPM().

    Use mixer.getCurrentTempo(asInt=True) to avoid any internal scaling
    and get the actual BPM value FL shows in the toolbar.
    """
    try:
        bpm = float(mixer.getCurrentTempo(True))
        return max(20.0, min(999.0, bpm))
    except Exception:
        return 120.0


def ensureMetronomeOn():
    """Turn FL metronome on (FPT_Metronome toggles; repeat until UI reports on)."""
    try:
        if ui.isMetronomeEnabled():
            return
    except Exception:
        return
    for _ in range(4):
        transport.globalTransport(midi.FPT_Metronome, 1)
        try:
            if ui.isMetronomeEnabled():
                return
        except Exception:
            return


def ensureMetronomeOff():
    """Turn FL metronome off (FPT_Metronome toggles; repeat until UI reports off)."""
    try:
        if not ui.isMetronomeEnabled():
            return
    except Exception:
        return
    for _ in range(4):
        transport.globalTransport(midi.FPT_Metronome, 1)
        try:
            if not ui.isMetronomeEnabled():
                return
        except Exception:
            return


def log(msg):
    if DEBUG:
        print("[Lightpad] " + str(msg))


def logFaderSync(msg):
    if FADER_SYNC_DEBUG:
        print("[Lightpad] FADER " + str(msg))


_lastMidiErrorTime = 0.0


def sendLED(name, cc, value):
    global _lastMidiErrorTime
    if DEBUG:
        log(f"LED OUT {name} (CC {cc}) = {value}")
    try:
        device.midiOutMsg(midi.MIDI_CONTROLCHANGE, 0, cc, value)
    except Exception:
        t = time.time()
        if t - _lastMidiErrorTime >= 5.0:  # at most once per 5s
            _lastMidiErrorTime = t
            print("[Lightpad] ERROR sending MIDI OUT")


def sendRecord(value):
    global recordState
    if recordState != value:
        recordState = value
        sendLED("RECORD", BTN_RECORD, value)


def sendRecordToDevice(value):
    """Send record LED value to device without updating recordState (for re-assert during hold)."""
    try:
        device.midiOutMsg(midi.MIDI_CONTROLCHANGE, 0, BTN_RECORD, value)
    except Exception:
        pass


def sendMetro(value):
    global metroState
    if metroState != value:
        metroState = value
        sendLED("METRO", BTN_METRO, value)


def sendMetroToDevice(value):
    """Send metronome LED value without updating metroState."""
    try:
        device.midiOutMsg(midi.MIDI_CONTROLCHANGE, 0, BTN_METRO, value)
    except Exception:
        pass


def applyMetroSteadyLED():
    """Push steady metronome LED (64 on / 0 off) to the device and sync metroState.

    Always sends MIDI so the device state can’t stay stuck at 127 if script and pad disagree.
    """
    global metroState
    target = METRO_LED_STEADY_ON if metroEnabled else METRO_LED_OFF
    sendMetroToDevice(target)
    metroState = target


def sendPlay(value):
    global playState
    if playState != value:
        playState = value
        sendLED("PLAY", BTN_PLAY, value)


def sendStop(value):
    global stopState
    if stopState != value:
        stopState = value
        sendLED("STOP", BTN_STOP, value)


def getTargetTrack():
    try:
        t = mixer.trackNumber()
        if t > 0:
            return t
        ch = channels.selectedChannel()
        if ch >= 0:
            return channels.getTargetFxTrack(ch)
    except:
        pass
    return -1


def resolvePrimaryTargetTrack():
    """Track the current mixer or channel selection for pan, volume, solo, and mute."""
    global lastMixerTrackSeen, lastChannelSeen, currentPrimaryTargetTrack

    try:
        mixerTrack = mixer.trackNumber()
    except Exception:
        mixerTrack = -1

    try:
        channel = channels.selectedChannel()
    except Exception:
        channel = -1

    if mixerTrack != lastMixerTrackSeen:
        lastMixerTrackSeen = mixerTrack
        if mixerTrack > 0:
            currentPrimaryTargetTrack = mixerTrack
            return currentPrimaryTargetTrack

    if channel != lastChannelSeen:
        lastChannelSeen = channel
        if channel >= 0:
            try:
                currentPrimaryTargetTrack = channels.getTargetFxTrack(channel)
                if currentPrimaryTargetTrack > 0:
                    return currentPrimaryTargetTrack
            except Exception:
                pass

    if currentPrimaryTargetTrack > 0 and isValidTrack(currentPrimaryTargetTrack):
        return currentPrimaryTargetTrack

    if mixerTrack > 0:
        return mixerTrack

    if channel >= 0:
        try:
            fxTrack = channels.getTargetFxTrack(channel)
            if fxTrack > 0:
                return fxTrack
        except Exception:
            pass

    return -1


def syncPrimaryFaders(force=False):
    """Refresh pan, volume, solo, and mute LEDs when mixer/channel selection changes."""
    global lastPrimarySyncMixerTrack, lastPrimarySyncChannel, lastPrimarySyncFxTrack, lastPrimarySyncTargetTrack
    global lastPrimaryFaderSignature, pendingPrimaryFaderWrites, pendingPrimaryFaderNextSendAt

    try:
        mixerTrack = mixer.trackNumber()
    except Exception:
        mixerTrack = -1

    try:
        channel = channels.selectedChannel()
    except Exception:
        channel = -1

    try:
        fxTrack = channels.getTargetFxTrack(channel) if channel >= 0 else -1
    except Exception:
        fxTrack = -1

    track = resolvePrimaryTargetTrack()
    values = {
        112: int((safeGetPan(track) + 1) * 63.5) if isValidTrack(track) else None,
        113: int(safeGetVolume(track) * 127) if isValidTrack(track) else None,
        BTN_SOLO: (127 if safeIsTrackSolo(track) else LED_DIM) if isValidTrack(track) else None,
        BTN_MUTE: (127 if safeIsTrackMuted(track) else LED_DIM) if isValidTrack(track) else None,
    }
    signature = (
        mixerTrack,
        channel,
        fxTrack,
        values[112],
        values[113],
        values[BTN_SOLO],
        values[BTN_MUTE],
    )

    if not force and signature == lastPrimaryFaderSignature:
        return False

    lastPrimarySyncMixerTrack = mixerTrack
    lastPrimarySyncChannel = channel
    lastPrimarySyncFxTrack = fxTrack
    lastPrimarySyncTargetTrack = track
    lastPrimaryFaderSignature = signature
    pendingPrimaryFaderWrites = []
    pendingPrimaryFaderNextSendAt = time.time()

    if FADER_SYNC_DEBUG:
        logFaderSync(f"sync mixer={mixerTrack} channel={channel} fx={fxTrack} resolved={track}")

    try:
        if isValidTrack(track):
            for cc, v in (
                (112, values[112]),
                (113, values[113]),
                (BTN_SOLO, values[BTN_SOLO]),
                (BTN_MUTE, values[BTN_MUTE]),
            ):
                if v is None:
                    continue
                if lastValues.get(cc) != v:
                    pendingPrimaryFaderWrites.append((cc, v, track))

            if FADER_SYNC_DEBUG:
                logFaderSync(
                    "values "
                    + " ".join(
                        [
                            f"pan={values[112]}",
                            f"volume={values[113]}",
                            f"solo={values[BTN_SOLO]}",
                            f"mute={values[BTN_MUTE]}",
                        ]
                    )
                )
        elif FADER_SYNC_DEBUG:
            logFaderSync("values invalid-track")

    except Exception as exc:
        if FADER_SYNC_DEBUG:
            logFaderSync(f"sync error={exc}")

    return True


def flushPrimaryFaderSync(now):
    global pendingPrimaryFaderWrites, pendingPrimaryFaderNextSendAt

    if not pendingPrimaryFaderWrites:
        return

    if now < pendingPrimaryFaderNextSendAt:
        return

    cc, v, track = pendingPrimaryFaderWrites.pop(0)
    if lastValues.get(cc) != v:
        if FADER_SYNC_DEBUG:
            logFaderSync(
                f"send cc={cc} name={FADERS[cc]['name']} track={track} value={v} prev={lastValues.get(cc)}"
            )
        lastValues[cc] = v
        sendLED(f"FADER {cc}", cc, v)

    pendingPrimaryFaderNextSendAt = now + PRIMARY_FADER_SEND_INTERVAL


def getGenericFaderTrack(baseTrack, offset):
    try:
        track = baseTrack + offset
    except Exception:
        return -1
    return track if isValidTrack(track) else -1


def isValidTrack(t):
    try:
        return 0 <= t < mixer.trackCount()
    except:
        return False


def safeGetVolume(t):
    try: return mixer.getTrackVolume(t)
    except: return 0.0


def safeGetPan(t):
    try: return mixer.getTrackPan(t)
    except: return 0.0


def safeIsTrackSolo(t):
    try:
        return bool(mixer.isTrackSolo(t))
    except Exception:
        return False


def safeIsTrackMuted(t):
    try:
        return bool(mixer.isTrackMuted(t))
    except Exception:
        return False


def OnInit():
    global metroEnabled
    global lastMixerTrackSeen, lastChannelSeen, currentPrimaryTargetTrack
    log("Initializing Lightpad script")

    try:
        lastMixerTrackSeen = mixer.trackNumber()
    except Exception:
        lastMixerTrackSeen = -1
    try:
        lastChannelSeen = channels.selectedChannel()
    except Exception:
        lastChannelSeen = -1
    currentPrimaryTargetTrack = resolvePrimaryTargetTrack()
    try:
        metroEnabled = ui.isMetronomeEnabled()
    except Exception:
        metroEnabled = False
    sendStop(LED_DIM)
    sendPlay(LED_DIM)
    sendRecord(LED_DIM)
    syncPrimaryFaders(force=True)
    flushPrimaryFaderSync(time.time())


def handleTransport(cc, value, event):
    global metroLast127EdgeTime
    global precountEnabled, metroEnabled
    global countInSessionActive, recordArmed
    global countInStartTime, countInBeatLength, countInPhase, countInNextFlashAt
    global recordIsBright, recordBrightUntil, countInJustFinishedUntil, recordSolidHoldUntil
    global recordSolidAt, recordSolidNotBefore, waitingForRecordingStart, recordStartedAtBar1
    global metroBrightUntil, metroIsBright

    # STOP: gated (127 while down, 0 on release). Other transport CCs are toggles (127/0 alternate).
    if cc == BTN_STOP and value == 127:
        transport.stop()
        sendStop(127)
        countInSessionActive = False
        recordArmed = False
        countInPhase = 4
        countInJustFinishedUntil = 0.0
        recordSolidHoldUntil = 0.0
        recordSolidAt = 0.0
        recordSolidNotBefore = 0.0
        waitingForRecordingStart = False
        recordStartedAtBar1 = False
        return True

    if cc == BTN_STOP and value == 0:
        sendStop(LED_DIM)
        return True

    if cc == BTN_PLAY:
        wasPlaying = transport.isPlaying()

        if value >= 64:
            sendPlay(127)
        else:
            sendPlay(LED_DIM)
            if wasPlaying:
                sendStop(127)

        if not wasPlaying:
            transport.start()
            if recordArmed and precountEnabled:
                countInSessionActive = True
                countInStartTime = time.time()
                countInBeatLength = 60.0 / getBPM()
                countInPhase = 1
                countInNextFlashAt = countInStartTime + countInBeatLength
                sendRecord(127)
                recordIsBright = True
                recordBrightUntil = countInStartTime + PULSE_DURATION
                sendMetroToDevice(METRO_LED_FLASH)
                metroIsBright = True
                metroBrightUntil = countInStartTime + PULSE_DURATION
                if DEBUG:
                    log(f"Count-in timer armed: beatLength={countInBeatLength:.3f}s")
            else:
                countInSessionActive = False
                countInPhase = 4
        else:
            transport.stop()
            countInSessionActive = False
            countInPhase = 4
            countInJustFinishedUntil = 0.0
            recordSolidHoldUntil = 0.0
            recordSolidAt = 0.0
            recordSolidNotBefore = 0.0
            waitingForRecordingStart = False
            recordStartedAtBar1 = False

        return True

    if cc == BTN_RECORD:
        transport.record()
        try:
            recordArmed = transport.isRecording()
        except Exception:
            recordArmed = value >= 64
        return True

    if cc == BTN_METRO:
        now = time.time()
        # Toggle pad: 127 = metronome on in FL, 0 = off. Count-in: second 127 within
        # METRO_DOUBLE_127_PRECOUN_SEC of the previous 127 (0 in between is OK).
        if value >= 64:
            prev127 = metroLast127EdgeTime
            double_prec = prev127 > 0 and (now - prev127) <= METRO_DOUBLE_127_PRECOUN_SEC
            if double_prec:
                precountEnabled = not precountEnabled
                transport.globalTransport(midi.FPT_CountDown, 1)
            metroLast127EdgeTime = now
            ensureMetronomeOn()
            try:
                metroEnabled = bool(ui.isMetronomeEnabled())
            except Exception:
                pass
            applyMetroSteadyLED()
            if DEBUG:
                try:
                    if double_prec:
                        log(
                            "METRO double-127 -> count-in precount=%s ui=%s"
                            % (precountEnabled, ui.isMetronomeEnabled())
                        )
                    else:
                        log(
                            "METRO 127 -> on precount=%s ui=%s"
                            % (precountEnabled, ui.isMetronomeEnabled())
                        )
                except Exception:
                    log(
                        "METRO %s precount=%s"
                        % ("double-127 count-in" if double_prec else "127 on", precountEnabled)
                    )
        else:
            ensureMetronomeOff()
            try:
                metroEnabled = bool(ui.isMetronomeEnabled())
            except Exception:
                pass
            applyMetroSteadyLED()
            if DEBUG:
                try:
                    log(
                        "METRO 0 -> off precount=%s ui=%s"
                        % (precountEnabled, ui.isMetronomeEnabled())
                    )
                except Exception:
                    log("METRO 0 -> off precount=%s" % precountEnabled)

        return True

    return False


def OnMidiMsg(event):
    global isUserControlling, lastUserInputTime

    if event.status != midi.MIDI_CONTROLCHANGE:
        return

    cc = event.data1
    val = event.data2

    # First fader: let FL Studio handle CC1 (no script mapping).
    if cc == 1:
        return

    if DEBUG:
        log(f"MIDI IN CC {cc} = {val}")

    isUserControlling = True
    lastUserInputTime = time.time()

    if handleTransport(cc, val, event):
        event.handled = True
        return

    if cc in (BTN_SOLO, BTN_MUTE):
        track = resolvePrimaryTargetTrack()
        if not isValidTrack(track):
            return
        want_on = val >= 64
        try:
            if cc == BTN_SOLO:
                mixer.soloTrack(track, want_on)
            else:
                mixer.muteTrack(track, want_on)
        except Exception:
            pass
        if cc == BTN_SOLO:
            led = 127 if safeIsTrackSolo(track) else LED_DIM
        else:
            led = 127 if safeIsTrackMuted(track) else LED_DIM
        lastValues[cc] = led
        sendLED("SOLO" if cc == BTN_SOLO else "MUTE", cc, led)
        event.handled = True
        return

    if cc not in FADERS:
        return

    try:
        if cc in (112, 113):
            track = resolvePrimaryTargetTrack()
            if not isValidTrack(track):
                return

            if cc == 113:
                mixer.setTrackVolume(track, val / 127.0)
            elif cc == 112:
                mixer.setTrackPan(track, (val / 63.5) - 1.0)
        elif 116 <= cc <= 127:
            track = getTargetTrack()
            if not isValidTrack(track):
                return
            genericTrack = getGenericFaderTrack(track, cc - 116)
            if genericTrack >= 0:
                mixer.setTrackVolume(genericTrack, val / 127.0)

        event.handled = True

    except:
        pass


def OnUpdateBeatIndicator(value):
    global metroBrightUntil, metroIsBright
    global recordBrightUntil, recordIsBright, countInSessionActive, recordStartedAtBar1, waitingForRecordingStart

    # FL calls this with different values; we only care about 1/2 (on-beat)
    if value not in (1, 2):
        return

    playing = transport.isPlaying()
    recording = transport.isRecording()

    try:
        pos = transport.getSongPos()
    except Exception:
        pos = 999

    # Debug: log FL beat callback around bar 1 so we can see exact timing
    if DEBUG and (0.75 <= pos <= 1.25 or waitingForRecordingStart):
        log(f"FL beat value={value} pos={pos:.3f} playing={playing} recording={recording} waitingForRec={waitingForRecordingStart}")

    # Count-in LED beats: use session + phase (song pos can stay at 0 or jump during pre-roll).
    isCountingIn = countInSessionActive and 0 < countInPhase < 4

    # METRO: flash on each FL beat when metronome is on, or on each beat during scripted count-in.
    if ui.isMetronomeEnabled() or isCountingIn:
        sendMetroToDevice(METRO_LED_FLASH)
        metroIsBright = True
        metroBrightUntil = time.time() + PULSE_DURATION

    if isCountingIn:
        sendRecord(127)
        recordIsBright = True
        recordBrightUntil = time.time() + PULSE_DURATION
    elif countInSessionActive and pos >= 1.0:
        # Don't clear during an active timer-driven count-in: getSongPos() can sit at or past 1.0
        # during pre-roll, which would kill beats 2–4 (and metro flashes) on the channel script.
        beat_ok = countInBeatLength >= 0.2 and countInStartTime > 0
        if not (beat_ok and 0 < countInPhase < 4):
            # Count‑in finished or no valid timer window; stop flashing record on further beats.
            countInSessionActive = False

    # First beat callback after count-in = recording actually started; signal OnIdle to go solid
    if waitingForRecordingStart and value in (1, 2) and not recordStartedAtBar1:
        recordStartedAtBar1 = True
        if DEBUG:
            log(f"record start detected pos={pos:.3f} -> will set record solid on next OnIdle")


def OnIdle():
    """Runs every frame. Do not log here or in hot paths (sendRecord/sendMetro)."""
    global metroIsBright, metroBrightUntil, recordIsBright, recordBrightUntil, playState
    global metroEnabled, metroState
    global countInSessionActive, countInPhase, countInNextFlashAt, countInJustFinishedUntil
    global recordSolidHoldUntil, recordSolidAt, recordSolidNotBefore, waitingForRecordingStart, recordStartedAtBar1
    global _lastRecording, _lastPlaying, _lastRecordHoldSend

    now = time.time()

    recording = transport.isRecording()
    playing = transport.isPlaying()
    if DEBUG and _lastRecording is not None and _lastRecording != recording:
        log(f"recording state -> {recording}")
    if DEBUG and _lastPlaying is not None and _lastPlaying != playing:
        log(f"playing state -> {playing}")
    _lastRecording = recording
    _lastPlaying = playing

    if playState != (127 if playing else LED_DIM):
        sendPlay(127 if playing else LED_DIM)

    try:
        pos = transport.getSongPos()
    except Exception:
        pos = 999

    syncPrimaryFaders()
    flushPrimaryFaderSync(now)

    # Keep script state in sync when metronome is toggled from FL (toolbar / keyboard).
    try:
        ui_metro = bool(ui.isMetronomeEnabled())
    except Exception:
        ui_metro = metroEnabled
    if ui_metro != metroEnabled:
        metroEnabled = ui_metro
        if metroEnabled:
            sendMetro(METRO_LED_STEADY_ON)
        else:
            sendMetro(METRO_LED_OFF)

    # METRO steady: on = 64 (dim), off = 0 (matches Littlefoot; beat flash is separate).
    metroTarget = METRO_LED_STEADY_ON if metroEnabled else METRO_LED_OFF
    if metroIsBright and now > metroBrightUntil:
        sendMetroToDevice(metroTarget)
        metroIsBright = False

    if metroState != metroTarget:
        if DEBUG:
            try:
                log(f"METRO sync: target={metroTarget} metroEnabled={metroEnabled} precountEnabled={precountEnabled} ui={ui.isMetronomeEnabled()} playing={playing} recording={recording}")
            except Exception:
                log(f"METRO sync: target={metroTarget} metroEnabled={metroEnabled} precountEnabled={precountEnabled}")
        sendMetro(metroTarget)

    # RECORD: dim after each flash (during count-in or right after 4th beat)
    if (countInSessionActive or waitingForRecordingStart) and recordIsBright and now > recordBrightUntil:
        sendRecord(LED_DIM)
        recordIsBright = False

    # Timer-driven count-in (backup when FL doesn't call OnUpdateBeatIndicator during count-in).
    beat_ok = countInBeatLength >= 0.2 and countInStartTime > 0
    # Do not add log() here: OnIdle runs every frame and would scroll the console.
    # Beats 2–4 (beat 1 was fired in handleTransport)
    if countInSessionActive and countInPhase < 4 and beat_ok:
        if now >= countInNextFlashAt and not recordIsBright:
            sendRecord(127)
            recordIsBright = True
            recordBrightUntil = now + PULSE_DURATION
            sendMetroToDevice(METRO_LED_FLASH)
            metroIsBright = True
            metroBrightUntil = now + PULSE_DURATION
            countInPhase += 1
            countInNextFlashAt = countInStartTime + countInPhase * countInBeatLength
            # As soon as 4th beat fires, stop count-in so OnUpdateBeatIndicator won't re-light the LED.
            if countInPhase >= 4:
                countInSessionActive = False
                countInJustFinishedUntil = now + 1.0
                waitingForRecordingStart = True
                recordSolidAt = now + RECORD_WAIT_TIMEOUT
                recordSolidNotBefore = now + RECORD_DIM_MIN_BEATS * countInBeatLength
    elif countInSessionActive and countInPhase >= 4:
        # Dim after 4th beat pulse; session already cleared above so beat callback won't re-light.
        if not recordIsBright:
            countInSessionActive = False
    elif waitingForRecordingStart and now >= recordSolidNotBefore and (recordStartedAtBar1 or now >= recordSolidAt):
        # Go solid when we're past min dim time AND we've seen the first beat after count-in.
        why = "record start (beat)" if recordStartedAtBar1 else "timeout"
        waitingForRecordingStart = False
        recordStartedAtBar1 = False
        recordSolidAt = 0.0
        recordSolidNotBefore = 0.0
        recordSolidHoldUntil = now + 0.5
        if DEBUG:
            try:
                p = transport.getSongPos()
                log(f"record solid: {why} (pos={p:.3f} playing={transport.isPlaying()} recording={recording})")
            except Exception:
                log(f"record solid: {why}")
        sendRecord(127)
    else:
        # Keep record LED solid when recording, or while re-asserting after count-in.
        # While waitingForRecordingStart we stay dim until the "go solid" branch runs; don't send 127 here.
        hold = recordSolidHoldUntil > 0 and now < recordSolidHoldUntil
        if (recording or hold) and not waitingForRecordingStart:
            sendRecord(127)
            # Re-send 127 to device periodically; device may clear LED when we send METRO/FADER
            global _lastRecordHoldSend
            if now - _lastRecordHoldSend >= RECORD_HOLD_RESEND_INTERVAL:
                _lastRecordHoldSend = now
                sendRecordToDevice(127)
        if recordSolidHoldUntil > 0 and now >= recordSolidHoldUntil:
            recordSolidHoldUntil = 0.0
        if not (recording or hold) and now > countInJustFinishedUntil:
            if DEBUG and recordState != LED_DIM:
                log("record dim: not recording (past grace)")
            sendRecord(LED_DIM)


def OnRefresh(flags):

    global isUserControlling, lastUserInputTime, recordArmed

    if isUserControlling and time.time() - lastUserInputTime > USER_TIMEOUT:
        isUserControlling = False

    # Keep recordArmed in sync when user arms record from FL (e.g. keyboard).
    if not transport.isPlaying() and transport.isRecording():
        recordArmed = True

    if isUserControlling:
        return

    syncPrimaryFaders()
    flushPrimaryFaderSync(time.time())