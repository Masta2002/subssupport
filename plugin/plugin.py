from . import _
from Components.ActionMap import ActionMap
from Components.Sources.List import List
from Components.PluginComponent import PluginDescriptor
from Components.config import config
from Screens.Screen import Screen
from Screens.Setup import Setup

from .subtitles import E2SubsSeeker, SubsSearch, initSubsSettings, \
    SubsSetupGeneral, SubsSearchSettings, SubsSetupExternal, SubsSetupEmbedded
from .subtitlesdvb import SubsSupportDVB, SubsSetupDVBPlayer


def openSubtitlesSearch(session, **kwargs):
    settings = initSubsSettings().search
    eventList = []
    eventNow = session.screen["Event_Now"].getEvent()
    eventNext = session.screen["Event_Next"].getEvent()
    if eventNow:
        eventList.append(eventNow.getEventName())
    if eventNext:
        eventList.append(eventNext.getEventName())
    session.open(SubsSearch, E2SubsSeeker(session, settings), settings, searchTitles=eventList, standAlone=True)


def openSubtitlesPlayer(session, **kwargs):
    SubsSupportDVB(session)


def openSubsSupportSettings(session, **kwargs):
    settings = initSubsSettings()
    session.open(SubsSupportSettings, settings, settings.search, settings.external, settings.embedded, config.plugins.subsSupport.dvb)


class SubsSupportSettings(Screen):
    skin = """
        <screen position="center,center" size="400,220" resolution="1280,720">
            <widget source="menuList" render="Listbox" scrollbarMode="showOnDemand" position="10,30" size="380,180" zPosition="3" transparent="1" >
                <convert type="TemplatedMultiContent">
                    {"templates":
                        {"default": (30, [
                            MultiContentEntryText(pos=(0, 0), size=(380, 30), font = 0, flags=RT_HALIGN_LEFT|RT_VALIGN_CENTER|RT_WRAP, text=0, color=0xFFFFFF)
                        ], True, "showOnDemand"),
                        },
                    "fonts": [gFont("Regular", 23)],
                    "itemHeight": 30
                    }
                </convert>
            </widget>
        </screen>
        """

    def __init__(self, session, generalSettings, searchSettings, externalSettings, embeddedSettings, dvbSettings):
        Screen.__init__(self, session)
        self.generalSettings = generalSettings
        self.searchSettings = searchSettings
        self.externalSettings = externalSettings
        self.embeddedSettings = embeddedSettings
        self.dvbSettings = dvbSettings
        self["menuList"] = List()
        self["actionmap"] = ActionMap(["OkCancelActions", "DirectionActions"],
        {
            "up": self["menuList"].selectNext,
            "down": self["menuList"].selectPrevious,
            "ok": self.confirmSelection,
            "cancel": self.close,
        })
        self.onLayoutFinish.append(self.layoutFinished)
        self.setTitle(_("SubsSupport settings"))

    def layoutFinished(self):
        self["menuList"].setList([
            (_("General settings"), "general"),
            (_("External subtitles settings"), "external"),
            (_("Embedded subtitles settings"), "embedded"),
            (_("Search settings"), "search"),
            (_("DVB player settings"), "dvb")])

    def confirmSelection(self):
        selection = self["menuList"].getCurrent()[1]
        if selection == "general":
            self.openGeneralSettings()
        elif selection == "external":
            self.openExternalSettings()
        elif selection == "embedded":
            self.openEmbeddedSettings()
        elif selection == "search":
            self.openSearchSettings()
        elif selection == "dvb":
            self.openDVBPlayerSettings()

    def openGeneralSettings(self):
        self.session.open(SubsSetupGeneral, self.generalSettings)

    def openSearchSettings(self):
        seeker = E2SubsSeeker(self.session, self.searchSettings, True)
        self.session.open(SubsSearchSettings, self.searchSettings, seeker, True)

    def openExternalSettings(self):
        self.session.open(SubsSetupExternal, self.externalSettings)

    def openEmbeddedSettings(self):
        self.session.open(Setup, "Subtitle")

    def openDVBPlayerSettings(self):
        self.session.open(SubsSetupDVBPlayer, self.dvbSettings)


def Plugins(**kwargs):
    from enigma import getDesktop
    screenwidth = getDesktop(0).size().width()
    if screenwidth and screenwidth == 1920:
        iconSET = 'ss_set_FHD.png'
        iconDWN = 'ss_dwn_FHD.png'
        iconPLY = 'ss_ply_FHD.png'
    else:
        iconSET = 'ss_set_HD.png'
        iconDWN = 'ss_dwn_HD.png'
        iconPLY = 'ss_ply_HD.png'

    return [
        PluginDescriptor(name=_('SubsSupport settings'), icon=iconSET, description=_('Change subssupport settings'), where=PluginDescriptor.WHERE_PLUGINMENU, fnc=openSubsSupportSettings),
        PluginDescriptor(name=_('SubsSupport downloader'), icon=iconDWN, description=_('Download subtitles for your videos'), where=PluginDescriptor.WHERE_PLUGINMENU, fnc=openSubtitlesSearch),
        PluginDescriptor(name=_('SubsSupport DVB player'), icon=iconPLY, description=_('watch DVB broadcast with subtitles'), where=PluginDescriptor.WHERE_PLUGINMENU, fnc=openSubtitlesPlayer),
        PluginDescriptor(name=_('SubsSupport settings'), where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=openSubsSupportSettings),
        PluginDescriptor(name=_('SubsSupport downloader'), where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=openSubtitlesSearch),
        PluginDescriptor(name=_('SubsSupport DVB player'), where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=openSubtitlesPlayer)
           ]
