package com.naenyn.lightpad.bitwig;

import com.bitwig.extension.callback.BooleanValueChangedCallback;
import com.bitwig.extension.callback.EnumValueChangedCallback;
import com.bitwig.extension.callback.IntegerValueChangedCallback;
import com.bitwig.extension.controller.ControllerExtensionDefinition;
import com.bitwig.extension.controller.api.ControllerHost;
import com.bitwig.extension.controller.api.CursorDeviceFollowMode;
import com.bitwig.extension.controller.api.CursorRemoteControlsPage;
import com.bitwig.extension.controller.api.CursorTrack;
import com.bitwig.extension.controller.api.PinnableCursorDevice;
import com.bitwig.extension.controller.api.Parameter;
import com.bitwig.extension.controller.api.Preferences;
import com.bitwig.extension.controller.api.SettableEnumValue;
import com.bitwig.extension.controller.api.SettableRangedValue;

public class LightpadBlockExtension extends AbstractLightpadBlockExtension
{
   private static final int DEFAULT_CC_SOLO = 106;
   private static final int DEFAULT_CC_MUTE = 107;
   private static final int DEFAULT_CC_PAN = 112;
   private static final int DEFAULT_CC_VOLUME = 113;
   private static final int DEFAULT_CC_GENERIC_FIRST = 116;

   /** Labels for {@linkplain #remoteFaderBanksTargetPreference}; must match enum option strings. */
   private static final String REMOTE_TARGET_TRACK_HEADER = "Track header remotes";
   private static final String REMOTE_TARGET_SELECTED_DEVICE = "Selected device remotes";

   private static final int REMOTE_CONTROL_COUNT = 8;
   private static final String REMOTE_CONTROLS_PAGE_TRACK = "Lightpad track remotes";
   private static final String REMOTE_CONTROLS_PAGE_DEVICE = "Lightpad device remotes";

   private CursorTrack cursorTrack;
   private PinnableCursorDevice remoteTargetDevice;
   private CursorRemoteControlsPage remoteControlsPageTrack;
   private CursorRemoteControlsPage remoteControlsPageDevice;
   private SettableEnumValue remoteFaderBanksTargetPreference;

   private int soloCc = DEFAULT_CC_SOLO;
   private int muteCc = DEFAULT_CC_MUTE;
   private int panCc = DEFAULT_CC_PAN;
   private int volumeCc = DEFAULT_CC_VOLUME;
   private int remoteCcFirst = DEFAULT_CC_GENERIC_FIRST;

   protected LightpadBlockExtension(final ControllerExtensionDefinition definition,
      final ControllerHost host)
   {
      super(definition, host);
   }

   @Override
   protected String driverLogNameInit()
   {
      return "ROLI Lightpad Block M (Enhanced Mixer) initialized";
   }

   @Override
   protected String driverLogNameExit()
   {
      return "ROLI Lightpad Block M (Enhanced Mixer) exited";
   }

   @Override
   protected void configureExtensionEarly(final ControllerHost host)
   {
      cursorTrack = host.createCursorTrack(
         "lightpad-cursor",
         "Lightpad Cursor",
         0,
         0,
         true);
      remoteTargetDevice = cursorTrack.createCursorDevice(
         "lightpad-remote-device",
         "Lightpad Remote Target",
         0,
         CursorDeviceFollowMode.FOLLOW_SELECTION);
      remoteTargetDevice.exists().markInterested();

      initMixerPreferences(host);
      createRemoteControlPagesDuringInit();
   }

   @Override
   protected void configureExtensionObserversAndSync(final ControllerHost host)
   {
      cursorTrack.volume().markInterested();
      cursorTrack.pan().markInterested();
      cursorTrack.volume().value().markInterested();
      cursorTrack.pan().value().markInterested();
      cursorTrack.mute().markInterested();
      cursorTrack.solo().markInterested();

      cursorTrack.volume().value().addValueObserver(MIDI_CC_RANGE,
         (IntegerValueChangedCallback) this::sendVolumeCcFeedback);
      cursorTrack.pan().value().addValueObserver(MIDI_CC_RANGE,
         (IntegerValueChangedCallback) this::sendPanCcFeedback);
      cursorTrack.mute().addValueObserver((BooleanValueChangedCallback) this::sendMuteCcFeedback);
      cursorTrack.solo().addValueObserver((BooleanValueChangedCallback) this::sendSoloCcFeedback);

      attachRemoteControlFeedbackObservers();
      remoteFaderBanksTargetPreference.addValueObserver(
         (EnumValueChangedCallback) v -> syncRemoteFaderFeedbackFromHost());
   }

   @Override
   protected void syncExtensionAfterTransportReady()
   {
      sendVolumeCcFeedback(midiFromParameterMidi7(cursorTrack.volume()));
      sendPanCcFeedback(midiFromParameterMidi7(cursorTrack.pan()));
      sendMuteCcFeedback(cursorTrack.mute().get());
      sendSoloCcFeedback(cursorTrack.solo().get());
      syncRemoteFaderFeedbackFromHost();
   }

   @Override
   protected void handleExtensionMidi(final int cc, final int value)
   {
      if (cc == soloCc)
      {
         cursorTrack.solo().set(value >= LED_DIM);
         return;
      }

      if (cc == muteCc)
      {
         cursorTrack.mute().set(value >= LED_DIM);
         return;
      }

      if (cc == volumeCc)
      {
         cursorTrack.volume().set(value, MIDI_CC_RANGE);
         return;
      }

      if (cc == panCc)
      {
         cursorTrack.pan().set(value, MIDI_CC_RANGE);
         return;
      }

      if (cc >= remoteCcFirst && cc < remoteCcFirst + REMOTE_CONTROL_COUNT)
      {
         applyRemoteControlValue(cc - remoteCcFirst, value);
      }
   }

   private void sendVolumeCcFeedback(final int midi7)
   {
      sendCc(volumeCc, midi7);
   }

   private void sendPanCcFeedback(final int midi7)
   {
      sendCc(panCc, midi7);
   }

   private void sendMuteCcFeedback(final boolean muted)
   {
      sendCc(muteCc, muted ? MIDI_ON : LED_DIM);
   }

   private void sendSoloCcFeedback(final boolean soloed)
   {
      sendCc(soloCc, soloed ? MIDI_ON : LED_DIM);
   }

   private void sendRemoteFaderCcFeedback(final int slot, final int midi7)
   {
      sendCc(remoteCcFirst + slot, midi7);
   }

   private static int midiFromParameterMidi7(final Parameter parameter)
   {
      return Math.min(MIDI_CC_RANGE - 1,
         Math.max(0, (int) Math.round(parameter.get() * (MIDI_CC_RANGE - 1))));
   }

   private void createRemoteControlPagesDuringInit()
   {
      remoteControlsPageTrack = cursorTrack.createCursorRemoteControlsPage(
         REMOTE_CONTROLS_PAGE_TRACK,
         REMOTE_CONTROL_COUNT,
         "");
      remoteControlsPageDevice = remoteTargetDevice.createCursorRemoteControlsPage(
         REMOTE_CONTROLS_PAGE_DEVICE,
         REMOTE_CONTROL_COUNT,
         "");
   }

   private boolean useSelectedDeviceRemotes()
   {
      return REMOTE_TARGET_SELECTED_DEVICE.equals(remoteFaderBanksTargetPreference.get());
   }

   private CursorRemoteControlsPage activeRemoteControlsPage()
   {
      return useSelectedDeviceRemotes() ? remoteControlsPageDevice : remoteControlsPageTrack;
   }

   private void attachRemoteControlFeedbackObservers()
   {
      for (int i = 0; i < REMOTE_CONTROL_COUNT; i++)
      {
         final int idx = i;
         final Parameter trackParam = remoteControlsPageTrack.getParameter(idx);
         trackParam.markInterested();
         trackParam.value().markInterested();
         trackParam.value().addValueObserver(MIDI_CC_RANGE,
            (IntegerValueChangedCallback) v -> {
               if (!useSelectedDeviceRemotes())
               {
                  sendRemoteFaderCcFeedback(idx, v);
               }
            });
         final Parameter deviceParam = remoteControlsPageDevice.getParameter(idx);
         deviceParam.markInterested();
         deviceParam.value().markInterested();
         deviceParam.value().addValueObserver(MIDI_CC_RANGE,
            (IntegerValueChangedCallback) v -> {
               if (useSelectedDeviceRemotes())
               {
                  sendRemoteFaderCcFeedback(idx, v);
               }
            });
      }
   }

   private void syncRemoteFaderFeedbackFromHost()
   {
      final CursorRemoteControlsPage page = activeRemoteControlsPage();
      for (int i = 0; i < REMOTE_CONTROL_COUNT; i++)
      {
         sendRemoteFaderCcFeedback(i, midiFromParameterMidi7(page.getParameter(i)));
      }
   }

   private void applyRemoteControlValue(final int slot, final int midi7)
   {
      final Parameter remoteParam = activeRemoteControlsPage().getParameter(slot);
      final double normalized = Math.min(1.0, Math.max(0.0, midi7 / 127.0));
      remoteParam.value().setImmediately(normalized);
   }

   private void initMixerPreferences(final ControllerHost host)
   {
      final Preferences preferences = host.getPreferences();
      final String ccCategory = "Control Change";

      remoteFaderBanksTargetPreference =
         preferences.getEnumSetting(
            "Remote fader banks target",
            ccCategory,
            new String[] {REMOTE_TARGET_TRACK_HEADER, REMOTE_TARGET_SELECTED_DEVICE},
            REMOTE_TARGET_SELECTED_DEVICE);
      remoteFaderBanksTargetPreference.markInterested();

      final SettableRangedValue soloSetting =
         preferences.getNumberSetting("Solo CC", ccCategory, 0, 127, 1, "", DEFAULT_CC_SOLO);
      final SettableRangedValue muteSetting =
         preferences.getNumberSetting("Mute CC", ccCategory, 0, 127, 1, "", DEFAULT_CC_MUTE);
      final SettableRangedValue panSetting =
         preferences.getNumberSetting("Pan CC", ccCategory, 0, 127, 1, "", DEFAULT_CC_PAN);
      final SettableRangedValue volumeSetting =
         preferences.getNumberSetting("Volume CC", ccCategory, 0, 127, 1, "", DEFAULT_CC_VOLUME);
      final SettableRangedValue remoteCcFirstSetting =
         preferences.getNumberSetting(
            "First remote fader CC",
            ccCategory,
            0,
            127,
            1,
            "",
            DEFAULT_CC_GENERIC_FIRST);

      soloSetting.markInterested();
      muteSetting.markInterested();
      panSetting.markInterested();
      volumeSetting.markInterested();
      remoteCcFirstSetting.markInterested();

      soloSetting.addValueObserver(MIDI_CC_RANGE, (IntegerValueChangedCallback) v -> soloCc = v);
      muteSetting.addValueObserver(MIDI_CC_RANGE, (IntegerValueChangedCallback) v -> muteCc = v);
      panSetting.addValueObserver(MIDI_CC_RANGE, (IntegerValueChangedCallback) v -> panCc = v);
      volumeSetting.addValueObserver(MIDI_CC_RANGE, (IntegerValueChangedCallback) v -> volumeCc = v);
      remoteCcFirstSetting.addValueObserver(
         MIDI_CC_RANGE, (IntegerValueChangedCallback) v -> remoteCcFirst = v);
   }
}
