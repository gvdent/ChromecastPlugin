#
# Author: Tsjippy
#
"""
<plugin key="Chromecast" name="Chromecast status and control plugin" author="Tsjippy" version="1.0.0" wikilink="http://www.domoticz.com/wiki/plugins/plugin.html" externallink="https://github.com/Tsjippy/ChromecastPlugin/">
    <description>
        <h2>Chromecast</h2><br/>
        This plugin add devices to Domoticz to control your chromecast, and to retrieve its current app, title, playing mode.<br/><br/>
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>Pause, Play or stop the app on the chromecast</li>
            <li>See current connected app, title and playing mode.</li>
        </ul>
        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Switch device - Playing mode</li>
            <li>Switch device - Connected app</li>
            <li>Volume device - See or adjust the current volume</li>
            <li>Text device - See current title</li>
        </ul>
        <h3>Configuration</h3>
        Just add your chromecast name
    </description>
    <params>
        <param field="Mode1" label="Chromecast name " width="200px" required="true"/>
        <param field="Mode6" label="Debug" width="100px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal" default="true" />
                <option label="Logging" value="File"/>
            </options>
        </param>
    </params>
</plugin>
"""
#############################################################################
#                      Imports                                              #
#############################################################################
import sys
import threading

try:
    import Domoticz
    debug = False
except ImportError:
    import fakeDomoticz as Domoticz
    debug = True

import pychromecast
from pychromecast.controllers.youtube import YouTubeController

#############################################################################
#                      Domoticz call back functions                         #
#############################################################################
class StatusListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast = cast
        self.Appname=""
        self.Volume=0

    def new_cast_status(self, status):
        if self.Appname != status.display_name:
            self.Appname = status.display_name
            Domoticz.Log("The app changed to "+status.display_name)
            UpdateDevice(4,0,str(self.Appname))

        if self.Volume != status.volume_level:
            self.Volume = status.volume_level
            Volume = int(self.Volume*100)
            Domoticz.Log("Updated volume to "+str(Volume))
            UpdateDevice(2,Volume,str(Volume))


class StatusMediaListener:
    def __init__(self, name, cast):
        self.name = name
        self.cast= cast
        self.Mode=""
        self.Title=""

    def new_media_status(self, status):
        #Domoticz.Log("Mediastatus "+str(status))
        if self.Mode != status.player_state:
            self.Mode = status.player_state

            if(self.Mode) == "PLAYING":
                self.Mode="Play"
            elif(self.Mode) == "PAUSED":
                self.Mode="Pause"
            elif(self.Mode) == "STOPPED":
                self.Mode="Stop"

            Domoticz.Log("The playing mode has changed to "+self.Mode)
            UpdateDevice(1,0,self.Mode)
        if self.Title != status.title:
            self.Title = status.title
            Domoticz.Log("The title is changed to  "+self.Title)
            UpdateDevice(3,0,self.Title)

class BasePlugin:
    enabled = False
    def __init__(self):
        #self.var = 123
        return

    def onStart(self):
        # Check if images are in database
        Domoticz.Status("Checking if images are loaded")
        if 'ChromecastLogo' not in Images: Domoticz.Image('ChromecastLogo.zip').Create()

        # Check if devices need to be created
        createDevices()

        if Parameters["Mode6"]=="Debug":
            DumpConfigToLog()

        Domoticz.Heartbeat(30)

        Domoticz.Status("Starting up")

        self.chromecast=ConnectChromeCast()

        if self.chromecast != "":
            Domoticz.Status("Registering listeners")

            thread = Thread(target = startListening, args = (self.chromecast, ))
            thread.start()

        return True

    def onHeartbeat(self):
        if self.chromecast == "":
            self.chromecast=ConnectChromeCast()

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level))
        if self.chromecast == "":
            Domoticz.Error("No chromecast is connected!")
        else:
            if Unit == 1:
                if Level == 10:
                    Domoticz.Log("Start playing on chromecast")
                    self.chromecast.media_controller.play()
                elif Level == 20:
                    Domoticz.Log("Pausing chromecast")
                    self.chromecast.media_controller.pause()
                elif Level == 30:
                    Domoticz.Log("Killing "+self.chromecast.app_display_name)
                    self.chromecast.quit_app()
            elif Unit == 2:
                vl = float(Level)/100
                self.chromecast.set_volume(vl)
            elif Unit == 4:
                if Level == 30:
                    Domoticz.Log("Starting Youtube on chromecast")
                    yt = YouTubeController()
                    self.chromecast.register_handler(yt)

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

    # Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return

#############################################################################
#                       Device specific functions                           #
#############################################################################

def senderror(e):
    Domoticz.Error('Error on line {}'.format(sys.exc_info()[-1].tb_lineno)+" Error is "+str(e))
    return

def createDevices():
    if 1 not in Devices:
        OPTIONS1 =  {   "LevelActions"  : "|||||",
                        "LevelNames"    : "Off|Play|Pause|Stop",
                        "LevelOffHidden": "true",
                        "SelectorStyle" : "0"
                    }
        Domoticz.Log("Created 'Status' device")
        Domoticz.Device(Name="Control", Unit=1, TypeName="Selector Switch", Switchtype=18, Options=OPTIONS1, Used=1).Create()
        UpdateImage(1, 'ChromecastLogo')

    if 2 not in Devices:
        Domoticz.Log("Created 'Volume' device")
        Domoticz.Device(Name="Volume", Unit=2, Type=244, Subtype=73, Switchtype=7, Used=1).Create()
        UpdateImage(2, 'ChromecastLogo')

    if 3 not in Devices:
        Domoticz.Log("Created 'Title' device")
        Domoticz.Device(Name="Title", Unit=3, Type=243, Subtype=19, Used=1).Create()
        UpdateImage(3, 'ChromecastLogo')

    if 4 not in Devices:
        OPTIONS4 =  {   "LevelActions"  : "|||||",
                        "LevelNames"    : "Off|Spotify|Netflix|Youtube|Other",
                        "LevelOffHidden": "true",
                        "SelectorStyle" : "0"
                    }
        Domoticz.Log("Created 'App' device")
        Domoticz.Device(Name="App name", Unit=4, TypeName="Selector Switch", Switchtype=18, Options=OPTIONS4, Used=1).Create()
        UpdateImage(4, 'ChromecastLogo')

    Domoticz.Log("Devices check done")
    return

# Synchronise images to match parameter in hardware page
def UpdateImage(Unit, Logo):
    if Unit in Devices and Logo in Images:
        if Devices[Unit].Image != Images[Logo].ID:
            Domoticz.Log("Device Image update: 'Chromecast', Currently " + str(Devices[Unit].Image) + ", should be " + str(Images[Logo].ID))
            Devices[Unit].Update(nValue=Devices[Unit].nValue, sValue=str(Devices[Unit].sValue), Image=Images[Logo].ID)
    return

def ConnectChromeCast():
    chromecast = ""
    try:
        ChromecastName = Parameters["Mode1"]
    except:
        ChromecastName="Test Device"

    Domoticz.Status("Checking for available chromecasts")
    try:
        chromecasts = pychromecast.get_chromecasts()
        if len(chromecasts) != 0:
            Domoticz.Log("Found these chromecasts: "+str(chromecasts))
        else:
            Domoticz.Status("No casting devices found, make sure they are online.")
    except Exception as e:
        senderror(e)

    if len(chromecasts) != 0:
        Domoticz.Status("Trying to connect to "+ChromecastName)
        try:
            chromecast = next(cc for cc in chromecasts if cc.device.friendly_name == ChromecastName)
            Domoticz.Status("Connected to " + ChromecastName)
        except StopIteration:
            Domoticz.Error("Could not connect to "+ChromecastName)
        except Exception as e:
            senderror(e)

    return chromecast

def startListening(chromecast):
    Domoticz.Log("Registering listeners")
    listenerCast = StatusListener(chromecast.name, chromecast)
    chromecast.register_status_listener(listenerCast)

    listenerMedia = StatusMediaListener(chromecast.name, chromecast)
    chromecast.media_controller.register_status_listener(listenerMedia)

    Domoticz.Log("Done registering listeners")

# Update Device into database
def UpdateDevice(Unit, nValue, sValue, AlwaysUpdate=False):
    # Make sure that the Domoticz device still exists (they can be deleted) before updating it
    if Unit in Devices:
        if Devices[Unit].nValue != nValue or Devices[Unit].sValue != sValue or AlwaysUpdate == True:
            Devices[Unit].Update(nValue, str(sValue))
            Domoticz.Log("Update " + Devices[Unit].Name + ": " + str(nValue) + " - '" + str(sValue) + "'")
    return

if debug==True:
    ConnectChromeCast()




