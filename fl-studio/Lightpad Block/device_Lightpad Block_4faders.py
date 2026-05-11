# name=ROLI Lightpad Block M (4 faders)
# supportedDevices=Lightpad Block

import mixer
import channels
import transport
import midi
import ui
import device
import time

DEBUG = False
FADER_SYNC_DEBUG = True

# Hardware / transport constants
DELAY_TRACK_NAME = "Delay"
REVERB_TRACK_NAME = "Reverb"

FADERS = {
    115: {"type": "volume", "name": "volume"},
    114: {"type": "pan", "name": "pan"},
    113: {"type": "reverb", "name": "reverb"},
    112: {"type": "delay", "name": "delay"},
}

for i, cc in enumerate(range(116, 128), start=1):
    FADERS[cc] = {"type": "generic", "name": f"fader{i}", "offset": i - 1}

BTN_STOP = 102
BTN_PLAY = 103
BTN_RECORD = 104
BTN_METRO = 105

# CCs we care about for debug (transport only; skip fader spam)
DEBUG_CCS = (BTN_STOP, BTN_PLAY, BTN_RECORD, BTN_METRO)

PULSE_DURATION = 0.12
LED_DIM = 64   # Dim level for flash (play/stop/record; metronome steady uses METRO_LED_*)
METRO_LED_OFF = 0
METRO_LED_STEADY_ON = 64
METRO_LED_FLASH = 127
METRO_REPEAT_MAX_GAP = 0.24
METRO_SHORT_COMMIT_DELAY = 0.21
METRO_LO_IGNORE_AFTER_SINGLE_HI = 0.05
METRO_SYNC_DELAY = 0.05
RECORD_HOLD_RESEND_INTERVAL = 0.05
PRIMARY_FADER_SEND_INTERVAL = 0.03

# Track lookup
delayTrack = -1
reverbTrack = -1
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

metroSyncPendingUntil = 0.0
precountEnabled = False
metroEnabled = False
metroLastHiAt = 0.0
metroFirstHiAt = 0.0
metroHiBurstCount = 0
metroLongCountInDone = False
metroShortPending = False

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


def requestMetroSync():
    global metroSyncPendingUntil
    metroSyncPendingUntil = time.time() + METRO_SYNC_DELAY


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
    """Track the current mixer or channel selection for the first four faders."""
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
    """Refresh the four primary faders when mixer/channel selection changes."""
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
        112: int(safeGetSend(track, delayTrack) * 127) if isValidTrack(track) and delayTrack >= 0 else None,
        113: int(safeGetSend(track, reverbTrack) * 127) if isValidTrack(track) and reverbTrack >= 0 else None,
        114: int((safeGetPan(track) + 1) * 63.5) if isValidTrack(track) else None,
        115: int(safeGetVolume(track) * 127) if isValidTrack(track) else None,
    }
    signature = (mixerTrack, channel, fxTrack, values[112], values[113], values[114], values[115])

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
            for cc, v in ((112, values[112]), (113, values[113]), (114, values[114]), (115, values[115])):
                if v is None:
                    continue
                if lastValues.get(cc) != v:
                    pendingPrimaryFaderWrites.append((cc, v, track))

            if FADER_SYNC_DEBUG:
                logFaderSync(
                    "values "
                    + " ".join(
                        [
                            f"delay={values[112]}",
                            f"reverb={values[113]}",
                            f"pan={values[114]}",
                            f"volume={values[115]}",
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


def safeGetSend(a, b):
    try: return mixer.getRouteToLevel(a, b)
    except: return 0.0


def findTrack(name):
    try:
        for i in range(mixer.trackCount()):
            if mixer.getTrackName(i).lower() == name.lower():
                return i
    except:
        pass
    return -1


def OnInit():
    global delayTrack, reverbTrack, metroEnabled
    global lastMixerTrackSeen, lastChannelSeen, currentPrimaryTargetTrack
    log("Initializing Lightpad script")

    delayTrack = findTrack(DELAY_TRACK_NAME)
    reverbTrack = findTrack(REVERB_TRACK_NAME)
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
    global metroLastHiAt, metroFirstHiAt, metroHiBurstCount, metroLongCountInDone, metroShortPending
    global precountEnabled, metroEnabled, countInSessionActive, recordArmed
    global countInStartTime, countInBeatLength, countInPhase, countInNextFlashAt
    global recordIsBright, recordBrightUntil, countInJustFinishedUntil, recordSolidHoldUntil
    global recordSolidAt, recordSolidNotBefore, waitingForRecordingStart, recordStartedAtBar1

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

        if value == 127:
            sendPlay(127)
            if not wasPlaying and recordArmed and precountEnabled:
                countInSessionActive = True
                countInStartTime = time.time()
                countInBeatLength = 60.0 / getBPM()
                # Fire first flash immediately (beat 1); timer will do beats 2–4
                countInPhase = 1
                countInNextFlashAt = countInStartTime + countInBeatLength
                sendRecord(127)
                recordIsBright = True
                recordBrightUntil = countInStartTime + PULSE_DURATION
                if DEBUG:
                    log(f"Count-in timer armed: beatLength={countInBeatLength:.3f}s")
            else:
                countInSessionActive = False
                countInPhase = 4
        else:
            # Play released or toggled off: if we're playing, we're stopping — cancel count-in
            sendPlay(LED_DIM)
            if wasPlaying:
                sendStop(127)
                countInSessionActive = False
                countInPhase = 4
                countInJustFinishedUntil = 0.0
                recordSolidHoldUntil = 0.0
                recordSolidAt = 0.0
                recordSolidNotBefore = 0.0
                waitingForRecordingStart = False
                recordStartedAtBar1 = False

        transport.start() if not wasPlaying else transport.stop()
        return True

    if cc == BTN_RECORD:
        recordArmed = (value == 127)
        transport.record()
        return True

    if cc == BTN_METRO:
        now = time.time()
        if value >= 64:
            gap = (now - metroLastHiAt) if metroLastHiAt > 0 else 999.0
            if gap >= METRO_REPEAT_MAX_GAP:
                metroLastHiAt = now
                metroFirstHiAt = now
                metroHiBurstCount = 1
                metroLongCountInDone = False
                metroShortPending = True
                if DEBUG:
                    try:
                        log(
                            "METRO 127 (arm short pending) precount=%s ui=%s"
                            % (precountEnabled, ui.isMetronomeEnabled())
                        )
                    except Exception:
                        log("METRO 127 (arm short pending) precount=%s" % precountEnabled)
            else:
                metroShortPending = False
                metroLastHiAt = now
                metroHiBurstCount += 1
                if (not metroLongCountInDone) and metroHiBurstCount >= 2:
                    metroLongCountInDone = True
                    precountEnabled = not precountEnabled
                    transport.globalTransport(midi.FPT_CountDown, 1)
                    try:
                        metroEnabled = bool(ui.isMetronomeEnabled())
                    except Exception:
                        pass
                    sendMetro(METRO_LED_STEADY_ON if metroEnabled else METRO_LED_OFF)
                    requestMetroSync()
                    if DEBUG:
                        try:
                            log(
                                "METRO 127 repeat -> count-in only precount=%s ui=%s"
                                % (precountEnabled, ui.isMetronomeEnabled())
                            )
                        except Exception:
                            log("METRO 127 repeat -> count-in only precount=%s" % precountEnabled)
        else:
            if (
                metroHiBurstCount == 1
                and metroLastHiAt > 0
                and (now - metroLastHiAt) < METRO_LO_IGNORE_AFTER_SINGLE_HI
            ):
                if DEBUG:
                    log("METRO 0 ignored (debounce after single 127)")
                return True
            metroLastHiAt = 0.0
            metroFirstHiAt = 0.0
            metroHiBurstCount = 0
            metroLongCountInDone = False
            metroShortPending = False
            ensureMetronomeOff()
            try:
                metroEnabled = bool(ui.isMetronomeEnabled())
            except Exception:
                metroEnabled = False
            sendMetro(METRO_LED_OFF)
            requestMetroSync()
            if DEBUG:
                try:
                    log(
                        "METRO 0 -> off, led=0 metroEnabled=%s ui=%s"
                        % (metroEnabled, ui.isMetronomeEnabled())
                    )
                except Exception:
                    log("METRO 0 -> off, led=0 metroEnabled=%s" % metroEnabled)

        return True

    return False


def OnMidiMsg(event):
    global isUserControlling, lastUserInputTime

    if event.status != midi.MIDI_CONTROLCHANGE:
        return

    cc = event.data1
    val = event.data2

    if DEBUG:
        log(f"MIDI IN CC {cc} = {val}")

    isUserControlling = True
    lastUserInputTime = time.time()

    if handleTransport(cc, val, event):
        event.handled = True
        return

    if cc not in FADERS:
        return

    try:
        if 112 <= cc <= 115:
            track = resolvePrimaryTargetTrack()
            if not isValidTrack(track):
                return

            if cc == 115:
                mixer.setTrackVolume(track, val / 127.0)
            elif cc == 114:
                mixer.setTrackPan(track, (val / 63.5) - 1.0)
            elif cc == 113 and reverbTrack >= 0:
                mixer.setRouteTo(track, reverbTrack, True)
                mixer.setRouteToLevel(track, reverbTrack, val / 127.0)
            elif cc == 112 and delayTrack >= 0:
                mixer.setRouteTo(track, delayTrack, True)
                mixer.setRouteToLevel(track, delayTrack, val / 127.0)
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

    # We only treat this as "count‑in" when a dedicated count‑in session
    # has been armed from the PLAY button and we're still before bar 1.0.
    # This prevents record from flashing during normal playback with
    # metronome turned on.
    isCountingIn = countInSessionActive and pos < 1.0

    # METRO: flash on every beat when enabled, but keep the steady LED
    # state managed separately so long-press count-in updates still work.
    if ui.isMetronomeEnabled():
        sendMetroToDevice(METRO_LED_FLASH)
        metroIsBright = True
        metroBrightUntil = time.time() + PULSE_DURATION

    if isCountingIn:
        sendRecord(127)
        recordIsBright = True
        recordBrightUntil = time.time() + PULSE_DURATION
    elif countInSessionActive and pos >= 1.0:
        # Count‑in just finished; stop the session so further beats
        # (normal playback) don't flash the record button.
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
    global _lastRecording, _lastPlaying, _lastRecordHoldSend, metroSyncPendingUntil
    global metroShortPending, metroFirstHiAt, metroHiBurstCount

    now = time.time()

    if (
        metroShortPending
        and metroHiBurstCount == 1
        and metroFirstHiAt > 0
        and (now - metroFirstHiAt) >= METRO_SHORT_COMMIT_DELAY
    ):
        metroShortPending = False
        ensureMetronomeOn()
        try:
            metroEnabled = bool(ui.isMetronomeEnabled())
        except Exception:
            metroEnabled = False
        sendMetro(METRO_LED_STEADY_ON if metroEnabled else METRO_LED_OFF)
        requestMetroSync()

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

    try:
        ui_metro = bool(ui.isMetronomeEnabled())
    except Exception:
        ui_metro = metroEnabled
    if ui_metro != metroEnabled:
        metroEnabled = ui_metro
        if metroEnabled:
            sendMetroToDevice(METRO_LED_FLASH)
            sendMetroToDevice(METRO_LED_STEADY_ON)
            metroState = METRO_LED_STEADY_ON
        else:
            sendMetro(METRO_LED_OFF)

    metroTarget = METRO_LED_STEADY_ON if metroEnabled else METRO_LED_OFF
    if metroIsBright and now > metroBrightUntil:
        sendMetroToDevice(metroTarget)
        metroIsBright = False

    if metroSyncPendingUntil and now >= metroSyncPendingUntil:
        metroSyncPendingUntil = 0.0
        try:
            metroEnabled = bool(ui.isMetronomeEnabled())
        except Exception:
            pass
        metroTarget = METRO_LED_STEADY_ON if metroEnabled else METRO_LED_OFF
        if DEBUG:
            try:
                log(f"METRO deferred sync: target={metroTarget} metroEnabled={metroEnabled} precountEnabled={precountEnabled} ui={ui.isMetronomeEnabled()} playing={playing} recording={recording}")
            except Exception:
                log(f"METRO deferred sync: target={metroTarget} metroEnabled={metroEnabled} precountEnabled={precountEnabled}")
        if metroEnabled:
            sendMetroToDevice(METRO_LED_FLASH)
            sendMetroToDevice(METRO_LED_STEADY_ON)
        else:
            sendMetroToDevice(METRO_LED_OFF)
        metroState = metroTarget

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