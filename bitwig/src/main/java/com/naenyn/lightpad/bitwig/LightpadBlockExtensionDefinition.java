package com.naenyn.lightpad.bitwig;

import java.util.UUID;

import com.bitwig.extension.api.PlatformType;
import com.bitwig.extension.controller.AutoDetectionMidiPortNamesList;
import com.bitwig.extension.controller.ControllerExtensionDefinition;
import com.bitwig.extension.controller.api.ControllerHost;

public class LightpadBlockExtensionDefinition extends ControllerExtensionDefinition
{
   private static final UUID DRIVER_ID = UUID.fromString("a8f7c2e4-6d1b-4a90-bc53-8f2e4d9c1a70");

   @Override
   public String getName()
   {
      return "ROLI Lightpad Block M (Enhanced Mixer)";
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
      return "Lightpad Block M";
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
      // Blocks expose ports such as "Lightpad Block EN3S" (device ID suffix). Bitwig matches these
      // discovery hints against actual port names (substring / prefix style), so the shared prefix is enough.
      list.add(new String[] {"Lightpad Block"}, new String[] {"Lightpad Block"});
   }

   @Override
   public LightpadBlockExtension createInstance(final ControllerHost host)
   {
      return new LightpadBlockExtension(this, host);
   }
}
