package com.naenyn.lightpad.bitwig;

import java.util.UUID;

import com.bitwig.extension.api.PlatformType;
import com.bitwig.extension.controller.AutoDetectionMidiPortNamesList;
import com.bitwig.extension.controller.ControllerExtensionDefinition;
import com.bitwig.extension.controller.api.ControllerHost;

/**
 * Same hardware as {@linkplain LightpadBlockExtensionDefinition}; {@linkplain #listAutoDetectionMidiPortNames}
 * is intentionally empty so Bitwig does not auto-install two controllers for one Lightpad — add this script
 * manually when using the four-fader Dashboard program.
 */
public class LightpadBlock4fadersExtensionDefinition extends ControllerExtensionDefinition
{
   private static final UUID DRIVER_ID = UUID.fromString("c4b51a8f-2e63-5d41-b870-a61f92e38d04");

   @Override
   public String getName()
   {
      return "ROLI Lightpad Block M (4 Faders)";
   }

   @Override
   public String getAuthor()
   {
      return "naenyn";
   }

   @Override
   public String getVersion()
   {
      return "1.0.0";
   }

   @Override
   public UUID getId()
   {
      return DRIVER_ID;
   }

   @Override
   public String getHardwareVendor()
   {
      return "Roli";
   }

   @Override
   public String getHardwareModel()
   {
      return "Lightpad Block M (4 Faders)";
   }

   @Override
   public int getRequiredAPIVersion()
   {
      return 21;
   }

   @Override
   public int getNumMidiInPorts()
   {
      return 1;
   }

   @Override
   public int getNumMidiOutPorts()
   {
      return 1;
   }

   @Override
   public void listAutoDetectionMidiPortNames(final AutoDetectionMidiPortNamesList list,
      final PlatformType platformType)
   {
   }

   @Override
   public LightpadBlock4fadersExtension createInstance(final ControllerHost host)
   {
      return new LightpadBlock4fadersExtension(this, host);
   }
}
