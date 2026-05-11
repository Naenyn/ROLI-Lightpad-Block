package com.naenyn.lightpad.bitwig;

import com.bitwig.extension.controller.ControllerExtensionDefinition;
import com.bitwig.extension.controller.api.ControllerHost;

/**
 * Transport-only mapping for the four-fader Littlefoot layout: matches stop/play/record/metro CC behavior
 * and LED feedback with {@linkplain LightpadBlockExtension}, but does not intercept solo/mute/pan/volume or
 * fader CCs so banks of sliders can reach the host for MIDI mapping or remote-control learning.
 */
public class LightpadBlock4fadersExtension extends AbstractLightpadBlockExtension
{
   protected LightpadBlock4fadersExtension(final ControllerExtensionDefinition definition,
      final ControllerHost host)
   {
      super(definition, host);
   }

   @Override
   protected String driverLogNameInit()
   {
      return "ROLI Lightpad Block M (4 Faders) initialized";
   }

   @Override
   protected String driverLogNameExit()
   {
      return "ROLI Lightpad Block M (4 Faders) exited";
   }

   @Override
   protected void configureExtensionEarly(final ControllerHost host)
   {
   }

   @Override
   protected void configureExtensionObserversAndSync(final ControllerHost host)
   {
   }

   @Override
   protected void syncExtensionAfterTransportReady()
   {
   }

   @Override
   protected void handleExtensionMidi(final int cc, final int value)
   {
   }
}
