package com.naenyn.lightpad.bitwig;

import com.bitwig.extension.api.util.midi.ShortMidiMessage;
import com.bitwig.extension.callback.BooleanValueChangedCallback;
import com.bitwig.extension.callback.DoubleValueChangedCallback;
import com.bitwig.extension.callback.IntegerValueChangedCallback;
import com.bitwig.extension.callback.ShortMidiMessageReceivedCallback;
import com.bitwig.extension.controller.ControllerExtension;
import com.bitwig.extension.controller.ControllerExtensionDefinition;
import com.bitwig.extension.controller.api.ControllerHost;
import com.bitwig.extension.controller.api.MidiOut;
import com.bitwig.extension.controller.api.NoteInput;
import com.bitwig.extension.controller.api.Preferences;
import com.bitwig.extension.controller.api.SettableRangedValue;
import com.bitwig.extension.controller.api.Transport;

/**
 * Shared transport (stop / play / record / metronome) MIDI handling and LED feedback for Lightpad Block
 * Bitwig extensions. Subclasses add mixer strip mapping and/or remote fader pages.
 */
abstract class AbstractLightpadBlockExtension extends ControllerExtension
{
   protected static final int DEFAULT_CC_STOP = 102;
   protected static final int DEFAULT_CC_PLAY = 103;
   protected static final int DEFAULT_CC_RECORD = 104;
   protected static final int DEFAULT_CC_METRO = 105;
   protected static final int CC_MOD = 1;

   protected static final int LED_DIM = 64;
   protected static final int MIDI_ON = 127;
   protected static final int MIDI_OFF = 0;
   protected static final int METRO_DOUBLE_MS = 550;
   protected static final int METRO_FLASH_RESTORE_MS = 120;
   protected static final int STOP_PULSE_MS = 60;
   protected static final int MIDI_CC_RANGE = 128;
   protected static final int MIDI_CHANNEL_1_CC_STATUS = 0xB0;

   protected Transport transport;
   protected MidiOut midiOut;
   protected ControllerHost controllerHost;
   protected int midiChannelZeroBased;

   protected int stopCc = DEFAULT_CC_STOP;
   protected int playCc = DEFAULT_CC_PLAY;
   protected int recordCc = DEFAULT_CC_RECORD;
   protected int metroCc = DEFAULT_CC_METRO;

   protected final int[] lastSentCc = new int[128];
   protected long metroLast127Ms;
   protected int timeSignatureDenominator = 4;
   protected long lastPulseBeatNumber = Long.MIN_VALUE;

   protected AbstractLightpadBlockExtension(
      final ControllerExtensionDefinition definition,
      final ControllerHost host)
   {
      super(definition, host);
   }

   protected abstract String driverLogNameInit();

   protected abstract String driverLogNameExit();

   /**
    * Transport CCs are handled here first; subclasses handle remaining CCs in
    * {@linkplain #handleExtensionMidi(int, int)}.
    */
   protected abstract void handleExtensionMidi(final int cc, final int value);

   @Override
   public void init()
   {
      controllerHost = (ControllerHost) getHost();
      transport = controllerHost.createTransport();
      midiOut = controllerHost.getMidiOutPort(0);

      for (int i = 0; i < lastSentCc.length; i++)
      {
         lastSentCc[i] = -1;
      }

      initTransportPreferences(controllerHost);
      configureExtensionEarly(controllerHost);

      final NoteInput noteInput = controllerHost.getMidiInPort(0).createNoteInput(
         "Lightpad Notes",
         "80????",
         "81????",
         "82????",
         "83????",
         "84????",
         "85????",
         "86????",
         "87????",
         "88????",
         "89????",
         "8A????",
         "8B????",
         "8C????",
         "8D????",
         "8E????",
         "8F????",
         "90????",
         "91????",
         "92????",
         "93????",
         "94????",
         "95????",
         "96????",
         "97????",
         "98????",
         "99????",
         "9A????",
         "9B????",
         "9C????",
         "9D????",
         "9E????",
         "9F????");
      noteInput.setShouldConsumeEvents(false);

      controllerHost.getMidiInPort(0).setMidiCallback((ShortMidiMessageReceivedCallback) this::onMidi);

      configureExtensionObserversAndSync(controllerHost);

      transport.isPlaying().markInterested();
      transport.isArrangerRecordEnabled().markInterested();
      transport.isMetronomeEnabled().markInterested();
      transport.preRoll().markInterested();
      transport.playPosition().markInterested();
      transport.timeSignature().denominator().markInterested();

      transport.isPlaying().addValueObserver((BooleanValueChangedCallback) this::onPlayingChanged);
      transport.isArrangerRecordEnabled().addValueObserver(
         (BooleanValueChangedCallback) this::onRecordArmChanged);
      transport.isMetronomeEnabled().addValueObserver(
         (BooleanValueChangedCallback) this::onMetronomeEnabledChanged);
      transport.playPosition().addValueObserver((DoubleValueChangedCallback) this::onPlayPositionChanged);
      transport.timeSignature().denominator().addValueObserver(
         (IntegerValueChangedCallback) this::onTimeSignatureDenominatorChanged);

      syncTransportLedsFromHost();
      syncExtensionAfterTransportReady();

      controllerHost.println(driverLogNameInit());
   }

   /**
    * Called after transport preferences and {@linkplain #initTransportPreferences}, before MIDI callback.
    * Mixer extension creates cursor track, remote pages, etc.
    */
   protected abstract void configureExtensionEarly(final ControllerHost host);

   /**
    * Register non-transport observers (e.g. cursor track) and initial LED sync for subclass features.
    */
   protected abstract void configureExtensionObserversAndSync(final ControllerHost host);

   /** LED / host sync after transport observers exist (strip LEDs, remote faders, or no-op). */
   protected abstract void syncExtensionAfterTransportReady();

   @Override
   public void exit()
   {
      controllerHost.println(driverLogNameExit());
   }

   @Override
   public void flush()
   {
   }

   private void onMidi(final ShortMidiMessage msg)
   {
      if (!msg.isControlChange())
      {
         return;
      }

      if (msg.getChannel() != midiChannelZeroBased)
      {
         return;
      }

      final int cc = msg.getData1();
      final int value = msg.getData2();

      if (cc == CC_MOD)
      {
         return;
      }

      if (handleTransportMidi(cc, value))
      {
         return;
      }

      handleExtensionMidi(cc, value);
   }

   /** @return true if this CC is transport-related and consumed */
   protected boolean handleTransportMidi(final int cc, final int value)
   {
      if (cc == stopCc)
      {
         if (value == MIDI_ON)
         {
            transport.stop();
            sendCc(stopCc, MIDI_ON);
            controllerHost.scheduleTask(() -> sendCc(stopCc, LED_DIM), STOP_PULSE_MS);
         }
         else
         {
            sendCc(stopCc, LED_DIM);
         }
         return true;
      }

      if (cc == playCc)
      {
         final boolean wasPlaying = transport.isPlaying().get();
         if (value >= LED_DIM)
         {
            sendCc(playCc, MIDI_ON);
            if (!wasPlaying)
            {
               transport.play();
            }
         }
         else
         {
            sendCc(playCc, LED_DIM);
            if (wasPlaying)
            {
               transport.stop();
               sendCc(stopCc, MIDI_ON);
               controllerHost.scheduleTask(() -> sendCc(stopCc, LED_DIM), STOP_PULSE_MS);
            }
         }
         return true;
      }

      if (cc == recordCc)
      {
         transport.record();
         return true;
      }

      if (cc == metroCc)
      {
         handleMetroCc(value);
         return true;
      }

      return false;
   }

   protected void initTransportPreferences(final ControllerHost host)
   {
      final Preferences preferences = host.getPreferences();
      final String midiCategory = "MIDI";
      final String ccCategory = "Control Change";

      final SettableRangedValue midiChSetting =
         preferences.getNumberSetting("MIDI channel", midiCategory, 1, 16, 1, "", 1);
      midiChSetting.markInterested();
      midiChSetting.addValueObserver(16,
         (IntegerValueChangedCallback) value -> midiChannelZeroBased =
            clampMidiChannelZeroBased(value - 1));

      final SettableRangedValue stopSetting =
         preferences.getNumberSetting("Stop CC", ccCategory, 0, 127, 1, "", DEFAULT_CC_STOP);
      final SettableRangedValue playSetting =
         preferences.getNumberSetting("Play CC", ccCategory, 0, 127, 1, "", DEFAULT_CC_PLAY);
      final SettableRangedValue recordSetting =
         preferences.getNumberSetting("Record CC", ccCategory, 0, 127, 1, "", DEFAULT_CC_RECORD);
      final SettableRangedValue metroSetting =
         preferences.getNumberSetting("Metronome CC", ccCategory, 0, 127, 1, "", DEFAULT_CC_METRO);

      stopSetting.markInterested();
      playSetting.markInterested();
      recordSetting.markInterested();
      metroSetting.markInterested();

      stopSetting.addValueObserver(MIDI_CC_RANGE, (IntegerValueChangedCallback) v -> stopCc = v);
      playSetting.addValueObserver(MIDI_CC_RANGE, (IntegerValueChangedCallback) v -> playCc = v);
      recordSetting.addValueObserver(MIDI_CC_RANGE, (IntegerValueChangedCallback) v -> recordCc = v);
      metroSetting.addValueObserver(MIDI_CC_RANGE, (IntegerValueChangedCallback) v -> metroCc = v);
   }

   protected void handleMetroCc(final int value)
   {
      final long now = System.currentTimeMillis();
      if (value >= LED_DIM)
      {
         final boolean doubleTap =
            metroLast127Ms > 0L && now - metroLast127Ms <= (long) METRO_DOUBLE_MS;
         metroLast127Ms = now;
         transport.isMetronomeEnabled().set(true);
         if (doubleTap)
         {
            togglePreRollShortcut();
         }
      }
      else
      {
         metroLast127Ms = 0L;
         transport.isMetronomeEnabled().set(false);
      }
      syncMetroSteadyLed();
   }

   protected void togglePreRollShortcut()
   {
      final String cur = transport.preRoll().get();
      if ("none".equals(cur))
      {
         transport.preRoll().set("one_bar");
      }
      else
      {
         transport.preRoll().set("none");
      }
   }

   private void onPlayingChanged(final boolean playing)
   {
      sendCc(playCc, playing ? MIDI_ON : LED_DIM);
      if (!playing)
      {
         lastPulseBeatNumber = Long.MIN_VALUE;
      }
      sendCc(stopCc, LED_DIM);
   }

   private void onRecordArmChanged(final boolean armed)
   {
      sendCc(recordCc, armed ? MIDI_ON : LED_DIM);
   }

   private void onMetronomeEnabledChanged(final boolean enabled)
   {
      syncMetroSteadyLed();
   }

   private void onPlayPositionChanged(final double playPositionInQuarterNotes)
   {
      if (!transport.isPlaying().get() || !transport.isMetronomeEnabled().get())
      {
         return;
      }

      final double beatLengthInQuarterNotes = 4.0 / Math.max(timeSignatureDenominator, 1);
      final long beatNumber =
         (long) Math.floor((playPositionInQuarterNotes / beatLengthInQuarterNotes) + 1e-9);
      if (beatNumber == lastPulseBeatNumber)
      {
         return;
      }

      lastPulseBeatNumber = beatNumber;
      sendCc(metroCc, MIDI_ON);
      controllerHost.scheduleTask(this::syncMetroSteadyLed, METRO_FLASH_RESTORE_MS);
   }

   private void onTimeSignatureDenominatorChanged(final int denominator)
   {
      if (denominator > 0)
      {
         timeSignatureDenominator = denominator;
      }
   }

   protected void syncMetroSteadyLed()
   {
      sendCc(metroCc, transport.isMetronomeEnabled().get() ? LED_DIM : MIDI_OFF);
   }

   protected void syncTransportLedsFromHost()
   {
      sendCc(playCc, transport.isPlaying().get() ? MIDI_ON : LED_DIM);
      sendCc(recordCc, transport.isArrangerRecordEnabled().get() ? MIDI_ON : LED_DIM);
      syncMetroSteadyLed();
      sendCc(stopCc, LED_DIM);
   }

   protected void sendCc(final int cc, final int value)
   {
      if (midiOut == null)
      {
         return;
      }
      if (lastSentCc[cc] == value)
      {
         return;
      }
      lastSentCc[cc] = value;
      midiOut.sendMidi(MIDI_CHANNEL_1_CC_STATUS | midiChannelZeroBased, cc, value);
   }

   protected static int clampMidiChannelZeroBased(final int ch)
   {
      if (ch < 0)
      {
         return 0;
      }
      if (ch > 15)
      {
         return 15;
      }
      return ch;
   }
}
