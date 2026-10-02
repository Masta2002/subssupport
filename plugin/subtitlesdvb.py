'''
Created on Sep 16, 2014

@author: marko
'''
import time

from Components.ActionMap import ActionMap, HelpableActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
from Components.Sources.StaticText import StaticText
from Components.config import config, configfile, getConfigListEntry, ConfigNothing, ConfigOnOff, ConfigSubsection, ConfigText
from Screens.HelpMenu import HelpableScreen
from Screens.MessageBox import MessageBox
from Screens.MinuteInput import MinuteInput
from Screens.Screen import Screen
from enigma import eTimer, eListboxPythonMultiContent, getDesktop, gFont, RT_HALIGN_LEFT
from skin import parseColor

from . import _
from .compat import eConnectCallback
from .e2_utils import getFps, fps_float, BaseMenuScreen, isFullHD, getDesktopSize
from .parsers.baseparser import ParseError
from .process import LoadError, DecodeError, ParserNotFoundError
from .subtitles import SubsChooser, initSubsSettings, SubsScreen, \
    SubsLoader, PARSERS, ALL_LANGUAGES_ENCODINGS, ENCODINGS, \
    SubsSetupExternal, warningMessage

config.plugins.subsSupport = ConfigSubsection()
config.plugins.subsSupport.dvb = ConfigSubsection()
config.plugins.subsSupport.dvb.autoSync = ConfigOnOff(default=True)
config.plugins.subsSupport.dvb.fpsDriftEnable = ConfigOnOff(default=False)

config.plugins.subsSupport.dvb.fpsRatio_23_976 = ConfigText(default="1.0000", fixed_size=False)
config.plugins.subsSupport.dvb.fpsRatio_24_000 = ConfigText(default="1.0000", fixed_size=False)
config.plugins.subsSupport.dvb.fpsRatio_25_000 = ConfigText(default="1.0000", fixed_size=False)
config.plugins.subsSupport.dvb.fpsRatio_29_970 = ConfigText(default="1.0000", fixed_size=False)
config.plugins.subsSupport.dvb.fpsRatio_30_000 = ConfigText(default="1.0000", fixed_size=False)

# video fps as returned by getFps(validOnly=True) -> drift ratio override
FPS_RATIO_SETTINGS = (
    ("23.976", config.plugins.subsSupport.dvb.fpsRatio_23_976),
    ("24.000", config.plugins.subsSupport.dvb.fpsRatio_24_000),
    ("25.000", config.plugins.subsSupport.dvb.fpsRatio_25_000),
    ("29.970", config.plugins.subsSupport.dvb.fpsRatio_29_970),
    ("30.000", config.plugins.subsSupport.dvb.fpsRatio_30_000),
)


class SubsSetupDVBPlayer(BaseMenuScreen):
    def __init__(self, session, dvbSettings):
        BaseMenuScreen.__init__(self, session, _("DVB player settings"), on_change=self._onEntryChanged)
        self.dvbSettings = dvbSettings

    def buildMenu(self):
        lst = []
        lst.append(getConfigListEntry(_("Auto sync to current event"), self.dvbSettings.autoSync))
        lst.append(getConfigListEntry(" ", ConfigNothing()))
        lst.append(getConfigListEntry(_("Try to correct FPS drift with FPS ratio"), config.plugins.subsSupport.dvb.fpsDriftEnable))
        if config.plugins.subsSupport.dvb.fpsDriftEnable.value:
            lst.append(getConfigListEntry(_("Subtitles late: Decrease Ratio. Subtitles rush: Increase Ratio"), ConfigNothing()))
            for fps, cfg in FPS_RATIO_SETTINGS:
                lst.append(getConfigListEntry(_("Override ratio for %s fps (standard is 1.0000)") % fps, cfg))
        self["config"].setList(lst)

    def _onEntryChanged(self):
        cur = self["config"].getCurrent()
        if cur and cur[1] is config.plugins.subsSupport.dvb.fpsDriftEnable:
            self.buildMenu()


class SubsSupportDVB(object):
    def __init__(self, session):
        self.session = session
        self.subsSettings = initSubsSettings()
        session.openWithCallback(self.subsChooserCB, SubsChooser, self.subsSettings, searchSupport=True, historySupport=True, titleList=self.getTitleList())

    def getTitleList(self):
        eventList = []
        eventNow = self.session.screen["Event_Now"].getEvent()
        eventNext = self.session.screen["Event_Next"].getEvent()
        if eventNow:
            eventList.append(eventNow.getEventName())
        if eventNext:
            eventList.append(eventNext.getEventName())
        return eventList

    def subsChooserCB(self, subfile=None, embeddedSubtitle=None, forceReload=False):
        if subfile is not None:
            subsLoader = SubsLoader(PARSERS, ALL_LANGUAGES_ENCODINGS + ENCODINGS[self.subsSettings.encodingsGroup.getValue()])
            try:
                subsList, subsEnc = subsLoader.load(subfile, fps=getFps(self.session))
            except LoadError:
                warningMessage(self.session, _("Cannot load subtitles. Invalid path"))
            except DecodeError:
                warningMessage(self.session, _("Cannot decode subtitles. Try another encoding group"))
            except ParserNotFoundError:
                warningMessage(self.session, _("Cannot parse subtitles. Not supported subtitles format"))
            except ParseError:
                warningMessage(self.session, _("Cannot parse subtitles. Invalid subtitles format"))
            else:
                self.subsScreen = self.session.instantiateDialog(SubsScreen, self.subsSettings.external)
                subsEngine = SubsEngineDVB(self.session, self.subsSettings.engine, self.subsScreen)
                subsEngine.setSubsList(subsList)
                self.session.openWithCallback(
                    self.subsControllerCB,
                    SubsControllerDVB,
                    subsEngine,
                    config.plugins.subsSupport.dvb.autoSync.value,
                    False,
                    None,
                    self.subsSettings.external
                )
        else:
            print('[SubsSupportDVB] no subtitles selected, exit')

    def subsControllerCB(self):
        self.session.deleteDialog(self.subsScreen)


class SubtitlePicker(Screen):
    """
    Responsive subtitle-line picker with aligned columns and fixed-height rows.

    eListboxPythonMultiContent supports only one item height for the complete
    list.  Using a different height for each subtitle row causes misaligned
    columns and clipped entries, because the last processed row silently wins.
    This screen therefore uses one resolution-aware row height and displays up
    to two text lines per subtitle entry.
    """

    def __init__(self, session, subsList, currentIndex):
        self.subsList = subsList or []
        try:
            self.currentIndex = int(currentIndex)
        except Exception:
            self.currentIndex = 0

        self._configure_layout()
        Screen.__init__(self, session)
        self.setTitle(_("Select current subtitle line"))

        self["actions"] = ActionMap(
            ["OkCancelActions", "ColorActions", "SubtitlePickerActions"],
            {
                "ok": self.selectSubtitle,
                "green": self.selectSubtitle,
                "cancel": self.close,
                "red": self.close,
                "firstSubtitle": self.firstSubtitle,
                "lastSubtitle": self.lastSubtitle,
            },
            -1
        )

        self["subList"] = MenuList(
            [], enableWrapAround=True, content=eListboxPythonMultiContent
        )
        self["subList"].l.setItemHeight(self.row_height)
        self["subList"].l.setFont(0, gFont("Regular", self.row_font_size))

        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Select"))
        self["instruction"] = StaticText(_("Press OK to select subtitle line"))
        self["header_number"] = StaticText(_("No."))
        self["header_time"] = StaticText(_("Time"))
        self["header_text"] = StaticText(_("Subtitle"))

        self.updateSubtitleList()
        self.onLayoutFinish.append(self.setInitialSelection)

    def _configure_layout(self):
        """Build a conservative picker layout for SD, HD and Full-HD skins."""
        desktop = getDesktop(0).size()
        desktop_width = desktop.width()
        desktop_height = desktop.height()

        visible_rows = 10
        if desktop_width >= 1920:
            screen_width = min(1540, desktop_width - 120)
            self.row_height = 78
            self.row_font_size = 26
            header_font_size = 27
            instruction_font_size = 24
            footer_font_size = 26
            header_height = 42
            instruction_height = 38
            footer_height = 48
        elif desktop_width >= 1280:
            screen_width = min(1120, desktop_width - 80)
            self.row_height = 68
            self.row_font_size = 22
            header_font_size = 23
            instruction_font_size = 21
            footer_font_size = 22
            header_height = 38
            instruction_height = 34
            footer_height = 42
        else:
            screen_width = min(700, desktop_width - 20)
            visible_rows = 8  # SD: fewer rows, so two text lines still fit
            self.row_height = 58
            self.row_font_size = 18
            header_font_size = 19
            instruction_font_size = 17
            footer_font_size = 18
            header_height = 34
            instruction_height = 30
            footer_height = 38

        # Reserve space for visible_rows complete rows, shrink the rows on small
        # screens and keep the font small enough for two text lines per row.
        padding = 10
        instruction_y = 8
        header_y = instruction_y + instruction_height + 4
        list_y = header_y + header_height + 4
        max_screen_height = max(1, desktop_height - 20)
        fixed_height = list_y + 8 + footer_height + 8
        max_row_height = max(1, int((max_screen_height - fixed_height) / visible_rows))
        self.row_height = min(self.row_height, max_row_height)
        self.row_font_size = max(10, min(self.row_font_size, int((self.row_height - 12) / 2.3)))
        list_height = self.row_height * visible_rows
        footer_y = list_y + list_height + 8
        screen_height = footer_y + footer_height + 8
        list_width = screen_width - (padding * 2)

        self.number_width = max(64, int(list_width * 0.09))
        self.time_width = max(170, int(list_width * 0.23))
        self.subtitle_width = list_width - self.number_width - self.time_width

        self.number_x = 0
        self.time_x = self.number_width
        self.subtitle_x = self.number_width + self.time_width

        button_width = min(220, int((list_width - 12) / 2))
        green_x = padding + button_width + 12

        self.skin = """
            <screen name="SubtitlePicker" position="center,center" size="%(screen_width)d,%(screen_height)d">
                <widget source="instruction" render="Label" position="%(padding)d,%(instruction_y)d" size="%(list_width)d,%(instruction_height)d" font="Regular;%(instruction_font_size)d" valign="center" halign="center" foregroundColor="#FFFFFF" backgroundColor="#303030" />
                <widget source="header_number" render="Label" position="%(padding)d,%(header_y)d" size="%(number_width)d,%(header_height)d" font="Regular;%(header_font_size)d" foregroundColor="#FFFFFF" backgroundColor="#202020" />
                <widget source="header_time" render="Label" position="%(time_header_x)d,%(header_y)d" size="%(time_width)d,%(header_height)d" font="Regular;%(header_font_size)d" foregroundColor="#FFFFFF" backgroundColor="#202020" />
                <widget source="header_text" render="Label" position="%(subtitle_header_x)d,%(header_y)d" size="%(subtitle_width)d,%(header_height)d" font="Regular;%(header_font_size)d" foregroundColor="#FFFFFF" backgroundColor="#202020" />
                <widget name="subList" position="%(padding)d,%(list_y)d" size="%(list_width)d,%(list_height)d" scrollbarMode="showOnDemand" />
                <widget source="key_red" render="Label" position="%(padding)d,%(footer_y)d" size="%(button_width)d,%(footer_height)d" font="Regular;%(footer_font_size)d" valign="center" halign="center" foregroundColor="#FFFFFF" backgroundColor="#A00000" />
                <widget source="key_green" render="Label" position="%(green_x)d,%(footer_y)d" size="%(button_width)d,%(footer_height)d" font="Regular;%(footer_font_size)d" valign="center" halign="center" foregroundColor="#FFFFFF" backgroundColor="#008000" />
            </screen>
        """ % {
            "screen_width": screen_width,
            "screen_height": screen_height,
            "padding": padding,
            "header_y": header_y,
            "header_height": header_height,
            "header_font_size": header_font_size,
            "instruction_y": instruction_y,
            "instruction_height": instruction_height,
            "instruction_font_size": instruction_font_size,
            "number_width": self.number_width,
            "time_width": self.time_width,
            "subtitle_width": self.subtitle_width,
            "time_header_x": padding + self.time_x,
            "subtitle_header_x": padding + self.subtitle_x,
            "list_y": list_y,
            "list_width": list_width,
            "list_height": list_height,
            "footer_y": footer_y,
            "footer_height": footer_height,
            "footer_font_size": footer_font_size,
            "button_width": button_width,
            "green_x": green_x,
        }

    def firstSubtitle(self):
        """Jump to the first subtitle."""
        if self.subsList:
            self["subList"].moveToIndex(0)

    def lastSubtitle(self):
        """Jump to the final subtitle."""
        if self.subsList:
            self["subList"].moveToIndex(len(self.subsList) - 1)

    def selectSubtitle(self):
        """Return the highlighted subtitle index to the controller."""
        index = self["subList"].getSelectedIndex()
        if 0 <= index < len(self.subsList):
            self.close(index)

    def updateSubtitleList(self):
        """Populate the picker with aligned fixed-height multi-content rows."""
        menu_items = []
        vertical_padding = 6
        single_line_y = max(0, int((self.row_height - self.row_font_size) / 2))

        for subtitle in self.subsList:
            try:
                caption_number = "%d" % (int(subtitle.get("index", 0)) + 1)
            except Exception:
                caption_number = "?"

            timestamp = self.format_time(subtitle.get("start", 0))
            display_text = self._limit_display_lines(subtitle.get("text") or "", max_lines=2)

            row = [
                subtitle,
                MultiContentEntryText(
                    pos=(self.number_x + 6, single_line_y),
                    size=(self.number_width - 10, self.row_font_size + 6),
                    font=0,
                    text=caption_number,
                    flags=RT_HALIGN_LEFT
                ),
                MultiContentEntryText(
                    pos=(self.time_x + 6, single_line_y),
                    size=(self.time_width - 10, self.row_font_size + 6),
                    font=0,
                    text=timestamp,
                    flags=RT_HALIGN_LEFT
                ),
                MultiContentEntryText(
                    pos=(self.subtitle_x + 6, vertical_padding),
                    size=(self.subtitle_width - 12, self.row_height - (vertical_padding * 2)),
                    font=0,
                    text=display_text,
                    flags=RT_HALIGN_LEFT
                ),
            ]
            menu_items.append(row)

        self["subList"].l.setItemHeight(self.row_height)
        self["subList"].l.setList(menu_items)
        self["subList"].l.invalidate()

    def _limit_display_lines(self, text, max_lines=2):
        """Keep picker rows uniform while preserving common two-line subtitles."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return ""
        if len(lines) <= max_lines:
            return "\n".join(lines)
        visible = lines[:max_lines]
        visible[-1] = visible[-1] + " ..."
        return "\n".join(visible)

    def setInitialSelection(self):
        """Open the picker on the currently playing subtitle where possible."""
        if not self.subsList:
            return
        index = min(max(self.currentIndex, 0), len(self.subsList) - 1)
        self["subList"].moveToIndex(index)

    def format_time(self, seconds):
        """Convert a subtitle start time to hh:mm:ss,ms."""
        try:
            millisecs = max(0, int(round(float(seconds) * 1000)))
        except (TypeError, ValueError):
            millisecs = 0
        secs, millisecs = divmod(millisecs, 1000)
        minutes, secs = divmod(secs, 60)
        hours, minutes = divmod(minutes, 60)
        return "%02d:%02d:%02d,%03d" % (hours, minutes, secs, millisecs)


class DVBExternalStyleScreen(Screen, ConfigListScreen, HelpableScreen):
    """
    Live editor for the external subtitles settings passed in (subsSettings.external,
    see initExternalSettings()), every change is applied to the renderer at once.
    """
    skin = """
    <screen position="center,center" size="900,522">
        <widget name="config" position="10,10" size="880,450" scrollbarMode="showOnDemand" />
        <eLabel position="10,470" size="880,2" backgroundColor="grey" />
        <widget source="key_red" render="Label" position="10,480" size="280,30" font="Regular;24" />
        <widget source="key_green" render="Label" position="310,480" size="280,30" font="Regular;24" />
        <widget source="key_yellow" render="Label" position="610,480" size="280,30" font="Regular;24" />
        <eLabel name="" position="10,512" size="280,8" backgroundColor="#f5516d" zPosition="3" />
        <eLabel name="" position="310,512" size="280,8" backgroundColor="#92ef80" zPosition="3" />
        <eLabel name="" position="610,512" size="280,8" backgroundColor="#ffd65c" zPosition="3" />
    </screen>
    """

    def __init__(self, session, externalSettings, apply_cb):
        Screen.__init__(self, session)
        HelpableScreen.__init__(self)
        self.setTitle(_("External subtitles style (live)"))
        self.externalSettings = externalSettings
        self.apply_cb = apply_cb

        self["key_red"] = StaticText(_("Cancel"))
        self["key_green"] = StaticText(_("Save"))
        self["key_yellow"] = StaticText(_("Apply now"))

        # OK, LEFT/RIGHT, ChoiceBox and VirtualKeyBoard changes all end in on_change
        ConfigListScreen.__init__(self, [], session=session, on_change=self._onEntryChanged)

        self["actions"] = HelpableActionMap(self, "OkCancelActions",
        {
            "cancel": (self.keyCancel, _("cancel")),
        }, -1)

        self["coloractions"] = HelpableActionMap(self, "ColorActions",
        {
            "red": (self.keyCancel, _("cancel")),
            "green": (self.keySave, _("save")),
            "yellow": (self.keyApply, _("apply now")),
        }, -1)

        self.onLayoutFinish.append(self.buildMenu)

    def buildMenu(self):
        # same list as SubsSetupExternal, only set it when the entries changed (keeps the selection)
        lst = SubsSetupExternal.getConfigList(self.externalSettings)
        current = self["config"].list or []
        if len(lst) != len(current) or any(new[1] is not old[1] for new, old in zip(lst, current)):
            self["config"].setList(lst)

    def _apply_live(self):
        if callable(self.apply_cb):
            self.apply_cb()

    def _onEntryChanged(self):
        self.buildMenu()
        self._apply_live()

    def keyApply(self):
        self._apply_live()

    def keySave(self):
        for x in self["config"].list:
            x[1].save()
        configfile.save()
        self._apply_live()
        self.close(True)

    def keyCancel(self):
        for x in self["config"].list:
            x[1].cancel()
        self._apply_live()  # back to the saved style
        self.close(False)


class SubsControllerDVB(Screen, HelpableScreen):
    fpsChoices = ["23.976", "23.980", "24.000", "25.000", "29.970", "30.000"]

    def __init__(self, session, engine, autoSync=False, setSubtitlesFps=False, subtitlesFps=None, externalSettings=None):
        desktopSize = getDesktopSize()
        controllerVerticalOffset = 50
        windowPosition = (int(0.03 * desktopSize[0]), int(0.05 * desktopSize[1]) + controllerVerticalOffset)
        windowSize = (int(0.9 * desktopSize[0]), int(0.4 * desktopSize[1]))
        fontSize = 33 if isFullHD() else 22
        rowHeight = fontSize + 10
        rowStep = rowHeight + 10
        if isFullHD():
            instructionFontSize = 24
        elif desktopSize[0] >= 1280:
            instructionFontSize = 18
        else:
            instructionFontSize = 14
        instructionHeight = instructionFontSize + 10
        contentY = instructionHeight + 8
        leftWidth = int(0.4 * windowSize[0])
        rightX = int(0.6 * windowSize[0])
        rightWidth = int(0.4 * windowSize[0])
        self.skin = """
            <screen position="%(window_x)d,%(window_y)d" size="%(window_width)d,%(window_height)d" zPosition="2" backgroundColor="transparent" flags="wfNoBorder">
                <widget name="instruction" position="0,0" size="%(window_width)d,%(instruction_height)d" valign="center" halign="center" font="Regular;%(instruction_font_size)d" transparent="1" foregroundColor="#F7A900" shadowColor="#40101010" shadowOffset="2,2" />
                <widget name="subtitle" position="0,%(left_row_0)d" size="%(left_width)d,%(row_height)d" valign="center" halign="left" font="Regular;%(font_size)d" transparent="1" foregroundColor="#ffffff" shadowColor="#40101010" shadowOffset="2,2" />
                <widget name="subtitlesTime" position="0,%(left_row_1)d" size="%(left_width)d,%(row_height)d" valign="center" halign="left" font="Regular;%(font_size)d" transparent="1" foregroundColor="#ffffff" shadowColor="#40101010" shadowOffset="2,2" />
                <widget name="subtitlesPosition" position="0,%(left_row_2)d" size="%(left_width)d,%(row_height)d" valign="center" halign="left" font="Regular;%(font_size)d" transparent="1" foregroundColor="#ffffff" shadowColor="#40101010" shadowOffset="2,2" />
                <widget name="subtitlesFps" position="0,%(left_row_3)d" size="%(left_width)d,%(row_height)d" valign="center" halign="left" font="Regular;%(font_size)d" transparent="1" foregroundColor="#6F9EF5" shadowColor="#40101010" shadowOffset="2,2" />
                <widget name="eventName" position="%(right_x)d,%(right_row_0)d" size="%(right_width)d,%(row_height)d" valign="center" halign="left" font="Regular;%(font_size)d" transparent="1" foregroundColor="#ffffff" shadowColor="#40101010" shadowOffset="2,2" />
                <widget name="eventTime" position="%(right_x)d,%(right_row_1)d" size="%(right_width)d,%(row_height)d" valign="center" halign="left" font="Regular;%(font_size)d" transparent="1" foregroundColor="#ffffff" shadowColor="#40101010" shadowOffset="2,2" />
                <widget name="eventDuration" position="%(right_x)d,%(right_row_2)d" size="%(right_width)d,%(row_height)d" valign="center" halign="left" font="Regular;%(font_size)d" transparent="1" foregroundColor="#ffffff" shadowColor="#40101010" shadowOffset="2,2" />
            </screen>""" % {
                "window_x": windowPosition[0],
                "window_y": windowPosition[1],
                "window_width": windowSize[0],
                "window_height": windowSize[1],
                "instruction_height": instructionHeight,
                "instruction_font_size": instructionFontSize,
                "font_size": fontSize,
                "left_width": leftWidth,
                "row_height": rowHeight,
                "left_row_0": contentY,
                "left_row_1": contentY + rowStep,
                "left_row_2": contentY + (rowStep * 2),
                "left_row_3": contentY + (rowStep * 3),
                "right_x": rightX,
                "right_width": rightWidth,
                "right_row_0": contentY,
                "right_row_1": contentY + rowStep,
                "right_row_2": contentY + (rowStep * 2),
            }

        Screen.__init__(self, session)
        HelpableScreen.__init__(self)
        self.engine = engine
        self.engine.onRenderSub.append(self.onRenderSub)
        self.engine.onHideSub.append(self.onHideSub)
        self.engine.onPositionUpdate.append(self.onUpdateSubPosition)
        subtitlesFps = subtitlesFps and fps_float(subtitlesFps)
        if subtitlesFps and str(subtitlesFps) in self.fpsChoices:
            self.providedSubtitlesFps = subtitlesFps
        else:
            self.providedSubtitlesFps = None
        self.externalSettings = externalSettings
        self.hideTimer = eTimer()
        self.hideTimer_conn = eConnectCallback(self.hideTimer.timeout, self.hideStatus)
        self.hideTimerDelay = 5000
        self.eventTimer = eTimer()
        self.eventTimer_conn = eConnectCallback(self.eventTimer.timeout, self.updateEventStatus)
        self.subtitlesTimer = eTimer()
        self.subtitlesTimer_conn = eConnectCallback(self.subtitlesTimer.timeout, self.updateSubtitlesTime)
        self.subtitlesTimerStep = 500
        self._baseTime = 0
        self._accTime = 0
        self.statusLocked = False
        self["instruction"] = Label(_("Press RED to open subtitle picker - Press OK to hide/unhide - Press MENU to open subtitle style settings - Press INFO to open help screen"))
        self['subtitle'] = Label()
        self['subtitlesPosition'] = Label(_("Subtitles Position") + ":")
        self['subtitlesTime'] = Label(_("Subtitles Time") + ":")
        self['subtitlesFps'] = Label(_("Subtitles FPS") + ":")
        self["eventName"] = Label(_("Event Name") + ":")
        self["eventTime"] = Label(_("Event Time") + ":")
        self["eventDuration"] = Label(_("Event Duration") + ":")
        self['actions'] = HelpableActionMap(self, "SubtitlesDVBActions",
        {
            "showHideStatus": (self.showHideStatus, _("show/hide subtitles status")),
            "playPauseSub": (self.playPause, _("play/pause subtitles playback")),
            "pauseSub": (self.pause, _("pause subtitles playback")),
            "resumeSub": (self.resume, _("resumes subtitles playback")),
            "restartSub": (self.restart, _("restarts current subtitle")),
            "nextSub": (self.nextSkip, _("skip to next subtitle")),
            "nextSubMinute": (self.nextMinuteSkip, _("skip to next subtitle (minute jump)")),
            "nextSubManual": (self.nextManual, _("skip to next subtitle by setting time in minutes")),
            "prevSub": (self.previousSkip, _("skip to previous subtitle")),
            "prevSubMinute": (self.previousMinuteSkip, _("skip to previous subtitle (minute jump)")),
            "prevSubManual": (self.previousManual, _("skip previous subtitle by setting time in minutes")),
            "eventSync": (self.eventSync, _("skip subtitle to current event position")),
            "changeFps": (self.changeFps, _("change subtitles fps")),
            "openSubtitlePicker": (self.openSubtitlePicker, _("open Subtitle Picker")),
            "showHelp": (self.showHelp, _("show help")),
            "confirmClose": (self.confirmClose, _("exit (confirm)")),
            "externalStyle": (self.externalStyle, _("External style")),
        }, -1)

        try:
            from Screens.InfoBar import InfoBar
            InfoBar.instance.subtitle_window.hide()
        except Exception:
            pass
        self.onLayoutFinish.append(self.hideStatus)
        self.onLayoutFinish.append(self.engine.start)
        self.onLayoutFinish.append(self.startEventTimer)
        self.onLayoutFinish.append(self.startSubtitlesTimer)
        self.onLayoutFinish.append(self.showStatusWithTimer)
        if setSubtitlesFps and self.providedSubtitlesFps:
            self.onFirstExecBegin.append(self.setProvidedSubtitlesFps)
        if autoSync:
            self.onFirstExecBegin.append(self.eventSync)
        self.onClose.append(self.engine.close)
        self.onClose.append(self.delTimers)

    def applyExternalStyleNow(self):
        r = self.engine.renderer
        try:
            r.hideSubtitle()
        except Exception:
            pass
        if hasattr(r, "reloadSettings"):
            r.reloadSettings()
        self.engine.renderSub()

    def externalStyle(self):
        if self.externalSettings is None:
            self.session.open(MessageBox, _("External settings not provided!"), MessageBox.TYPE_ERROR, timeout=3)
            return
        self.session.open(
            DVBExternalStyleScreen,
            self.externalSettings,
            self.applyExternalStyleNow
    )

    def confirmClose(self):
        def cb(answer):
            if answer:
                self.close()

        self.session.openWithCallback(
            cb,
            MessageBox,
            _("Exit SubsSupport DVB player?"),
            MessageBox.TYPE_YESNO
        )

    def showHelp(self):
        txt = "\n".join([
            _("Controls:"),
            "",
            _("RED: Open Subtitle Picker"),
            _("YELLOW: Sync subtitle to current event"),
            _("BLUE: Change subtitles FPS"),
            _("OK: Show/Hide status panel"),
            _("LEFT: Previous subtitle"),
            _("RIGHT: Next subtitle"),
            _("UP/DOWN: Restart current subtitle"),
            _("PREV/REWIND (short): -1 minute"),
            _("NEXT/FF (short): +1 minute"),
            _("PREV (long): Manual -minutes jump"),
            _("NEXT (long): Manual +minutes jump"),
            _("EXIT: Exit (confirm)"),
            _("MENU: Show subtitle Style Settings"),
            _("INFO: Show this help"),
        ])
        self.session.open(MessageBox, txt, MessageBox.TYPE_INFO, timeout=20)

    def openSubtitlePicker(self):
        try:
            subtitleList = self.engine.getSubtitlesList()
            currentIndex = self.engine.getPosition()

            if not subtitleList:
                print("[SubsSupportDVB] no subtitles for the subtitle picker")
                return
            self.session.openWithCallback(self.onSubtitlePicked, SubtitlePicker, subtitleList, currentIndex)
        except Exception as e:
            print("[SubsSupportDVB] cannot open the subtitle picker: %s" % e)

    def onSubtitlePicked(self, index=None):
        if index is not None:
            self.engine.toSub(index)
            self.showStatus(True)

    def startEventTimer(self):
        self.eventTimer.start(500)

    def startSubtitlesTimer(self):
        self.subtitlesTimer.start(self.subtitlesTimerStep)

    def setProvidedSubtitlesFps(self):
        self.engine.setSubsFps(self.providedSubtitlesFps)
        self.updateSubtitlesFps()

    def onUpdateSubPosition(self, position):
        self.updateSubtitlesPosition(position)

    def onRenderSub(self, sub):
        if self['subtitle'].visible:
            self.updateSubtitle(sub, True)
        if self['subtitlesTime'].visible:
            self.updateSubtitlesTime(sub)

    def onHideSub(self, sub):
        if sub == self.engine.subsList[-1]:
            self.subtitlesTimer.stop()
        if self['subtitle'].visible:
            nextSubIdx = self.engine.subsList.index(sub) + 1
            if nextSubIdx >= len(self.engine.subsList) - 1:
                nextSub = None
            else:
                nextSub = self.engine.subsList[nextSubIdx]
            self.updateSubtitle(nextSub, active=False)

    def showStatusWithTimer(self):
        self.showStatus(True)

    def showStatus(self, withTimer=False):
        sub = self.engine.getCurrentSub()
        active = self.engine.renderer.subShown
        self.updateSubtitle(sub, active)
        self.updateSubtitlesFps()
        self.updateSubtitlesPosition()
        self.updateEventStatus()
        self['instruction'].visible = True
        self['subtitle'].visible = True
        self['subtitlesPosition'].visible = True
        self['subtitlesTime'].visible = True
        self['subtitlesFps'].visible = True
        self['eventName'].visible = True
        self['eventTime'].visible = True
        self['eventDuration'].visible = True
        if withTimer and not self.statusLocked:
            self.hideTimer.start(self.hideTimerDelay, True)

    def hideStatus(self):
        self['instruction'].visible = False
        self['subtitle'].visible = False
        self['subtitlesPosition'].visible = False
        self['subtitlesTime'].visible = False
        self['subtitlesFps'].visible = False
        self['eventName'].visible = False
        self['eventTime'].visible = False
        self['eventDuration'].visible = False

    def updateSubtitle(self, sub, active):
        if sub is None:
            self['subtitle'].setText("")
            return
        st = sub['start'] * self.engine.fpsRatio / 90000
        et = sub['end'] * self.engine.fpsRatio / 90000
        stStr = "%d:%02d:%02d" % ((st / 3600, st % 3600 / 60, st % 60))
        etStr = "%d:%02d:%02d" % ((et / 3600, et % 3600 / 60, et % 60))
        if active:
            self['subtitle'].instance.setForegroundColor(parseColor("#F7A900"))
            self['subtitle'].setText("%s ----> %s" % (stStr, etStr))
        else:
            self['subtitle'].instance.setForegroundColor(parseColor("#aaaaaa"))
            self['subtitle'].setText("%s ----> %s" % (stStr, etStr))

    def updateSubtitlesPosition(self, position=None):
        if position is None:
            position = self.engine.subsList.index(self.engine.getCurrentSub())
        self['subtitlesPosition'].setText("%s: %d / %d" % (_("Subtitles Position"), position + 1, len(self.engine.subsList)))

    def updateSubtitlesTime(self, sub=None):
        if sub:
            self._baseTime = sub['start'] * self.engine.fpsRatio / 90
            self._accTime = 0
            if not self.engine.isPaused():
                self.startSubtitlesTimer()
        else:
            self._accTime += self.subtitlesTimerStep
        self._subtitlesTime = self._baseTime + self._accTime
        if self['subtitlesTime'].visible:
            st = self._subtitlesTime / 1000
            time = "%d:%02d:%02d" % (st / 3600, st % 3600 / 60, st % 60)
            self['subtitlesTime'].setText("%s: %s" % (_("Subtitles Time"), time))

    def updateSubtitlesFps(self):
        subsFps = self.engine.getSubsFps()
        videoFps = getFps(self.session, True)
        if subsFps is None or videoFps is None:
            self['subtitlesFps'].setText("%s: %s" % (_("Subtitles FPS"), _("unknown")))
            return
        if subsFps == videoFps:
            if self.providedSubtitlesFps is not None:
                if self.providedSubtitlesFps == videoFps:
                    self['subtitlesFps'].setText("%s: %s (%s)" % (_("Subtitles FPS"), _("original"), _("original")))
                else:
                    self['subtitlesFps'].setText("%s: %s (%s)" % (_("Subtitles FPS"), _("original"), str(self.providedSubtitlesFps)))
            else:
                self['subtitlesFps'].setText("%s: %s" % (_("Subtitles FPS"), _("original")))
        else:
            if self.providedSubtitlesFps is not None:
                if self.providedSubtitlesFps == videoFps:
                    self['subtitlesFps'].setText("%s: %s (%s)" % (_("Subtitles FPS"), str(subsFps), _("original")))
                else:
                    self['subtitlesFps'].setText("%s: %s (%s)" % (_("Subtitles FPS"), str(subsFps), str(self.providedSubtitlesFps)))
            else:
                self['subtitlesFps'].setText("%s: %s" % (_("Subtitles FPS"), str(subsFps)))

    def updateEventStatus(self):
        event = self.session.screen["Event_Now"].getEvent()
        if event is not None:
            eventName = event.getEventName()
            if eventName:
                if self["eventName"].getText() != eventName:
                    self["eventName"].setText("%s" % eventName)
            else:
                self["eventName"].setText("%s" % (_("unknown")))
            eventStartTime = event.getBeginTime()
            if eventStartTime:
                ep = int(time.time()) - eventStartTime
                self["eventTime"].setText("%s: %d:%02d:%02d" % (_("Time"), ep / 3600, ep % 3600 / 60, ep % 60))
            else:
                self["eventTime"].setText("%s: %s" % (_("Event Time"), "0:00:00"))
            eventDuration = event.getDuration()
            if eventDuration:
                if eventStartTime:
                    eventProgress = int(time.time()) - eventStartTime
                    if eventProgress > eventDuration:
                        ed = 0
                    else:
                        ed = eventDuration
                else:
                    ed = eventDuration
                self["eventDuration"].setText("%s: %d:%02d:%02d" % (_("Duration"), ed / 3600, ed % 3600 / 60, ed % 60))
            else:
                self["eventTime"].setText("%s: %s" % (_("Event Duration"), "0:00:00"))
        else:
            self["eventName"].setText("")
            self["eventTime"].setText("")
            self["eventDuration"].setText("")

    def changeFps(self):
        subsFps = self.engine.getSubsFps()
        if subsFps is None:
            return
        try:
            nextIdx = (self.fpsChoices.index(str(subsFps)) + 1) % len(self.fpsChoices)
        except ValueError:
            nextIdx = 0
        self.engine.setSubsFps(fps_float(self.fpsChoices[nextIdx]))
        self.updateSubtitlesFps()
        sub = self.engine.getCurrentSub()
        active = self.engine.renderer.subShown
        self.updateSubtitle(sub, active)
        self.updateSubtitlesPosition()
        self.showStatus(True)

    def showHideStatus(self):
        if self['subtitle'].visible:
            self.statusLocked = False
            self.hideStatus()
        else:
            self.statusLocked = True
            self.showStatus()

    def eventSync(self):
        event = self.session.screen["Event_Now"].getEvent()
        if event is not None:
            progress = (int(time.time()) - event.getBeginTime()) * 1000
            self.engine.seekTo(progress)
        else:
            self.session.open(MessageBox, _("cannot sync to event, event is not available"), MessageBox.TYPE_INFO, simple=True, timeout=3)

    def playPause(self):
        if self.engine.isPaused():
            self.resume()
        else:
            self.pause()

    def pause(self):
        self.engine.pause()
        self.subtitlesTimer.stop()
        self.showStatus()

    def resume(self):
        self.engine.resume()
        self.startSubtitlesTimer()
        self.showStatus(True)

    def restart(self):
        self.engine.pause()
        self.engine.resume()
        self.showStatus(True)

    def nextSkip(self):
        self.engine.toNextSub()
        self.showStatus(True)

    def nextMinuteSkip(self):
        self.engine.seekRelative(60 * 1000)
        self.showStatus(True)

    def nextManual(self):
        def nextManualCB(minutes):
            if minutes > 0:
                self.engine.seekRelative(minutes * 60 * 1000)
                self.showStatus(True)
        self.session.openWithCallback(nextManualCB, MinuteInput)

    def previousSkip(self):
        self.engine.toPrevSub()
        self.showStatus(True)

    def previousMinuteSkip(self):
        self.engine.seekRelative(-60 * 1000)
        self.showStatus(True)

    def previousManual(self):
        def previousManualCB(minutes):
            if minutes > 0:
                self.engine.seekRelative(-minutes * 60 * 1000)
                self.showStatus(True)
        self.session.openWithCallback(previousManualCB, MinuteInput)

    def delTimers(self):
        self.hideTimer.stop()
        del self.hideTimer_conn
        del self.hideTimer
        self.eventTimer.stop()
        del self.eventTimer_conn
        del self.eventTimer
        self.subtitlesTimer.stop()
        del self.subtitlesTimer_conn
        del self.subtitlesTimer


class SubsEngineDVB(object):
    def __init__(self, session, engineSettings, renderer):
        self.session = session
        self.renderer = renderer
        self.delay = 0
        self.__position = 0
        self.subsFpsRatio = 1  # subtitles fps / video fps
        self.fpsRatio = 1  # subsFpsRatio * fps drift override, used for timing
        self.subsList = None
        self.paused = True
        self.waitTimer = eTimer()
        self.waitTimer_conn = eConnectCallback(self.waitTimer.timeout, self.doWait)
        self.hideTimer = eTimer()
        self.hideTimer_conn = eConnectCallback(self.hideTimer.timeout, self.hideTimerCallback)
        self.onRenderSub = []
        self.onHideSub = []
        self.onPositionUpdate = []

    def setSubsList(self, subsList):
        self.subsList = subsList

    def setSubsFps(self, subsFps):
        print("[SubsEngineDVB] setSubsFps - setting fps to %s" % str(subsFps))
        videoFps = getFps(self.session, True)
        if videoFps is None:
            print("[SubsEngineDVB] setSubsFps - cannot get video fps!")
        else:
            self.waitTimer.stop()
            self.hideTimer.stop()
            self.subsFpsRatio = subsFps / float(videoFps)
            self.fpsRatio = self.subsFpsRatio * self.getFpsDriftOverride()
            self.renderSub()
            if not self.paused:
                self.setRefTime()
                self.startHideTimer()

    def setPosition(self, position):
        if position > len(self.subsList) - 1:
            return
        self.__position = position
        for f in self.onPositionUpdate:
            f(self.__position)

    def getPosition(self):
        return self.__position

    position = property(getPosition, setPosition)

    def getSubsFps(self):
        videoFps = getFps(self.session, True)
        if videoFps is None:
            return None
        return fps_float(self.subsFpsRatio * videoFps)

    def getCurrentSub(self):
        return self.subsList[self.position]

    def _safeRatio(self, cfg, default=1.0):
        try:
            s = str(cfg.value).strip().replace(",", ".")
            v = float(s)
            # optional clamp to avoid insane values
            if v < 0.80 or v > 1.20:
                return default
            return v
        except ValueError:
            return default

    def getSubtitlesList(self):
        """Subtitle lines with start/end in seconds, for the line picker."""
        result = []
        for idx, sub in enumerate(self.subsList):
            text = "\n".join(row["text"] for row in sub["rows"]) if "rows" in sub else sub.get("text", "")
            # same time base as the controller (fps ratio applied)
            result.append({"index": idx, "text": text, "start": sub["start"] * self.fpsRatio / 90000, "end": sub["end"] * self.fpsRatio / 90000})
        return result

    def getFpsDriftOverride(self):
        if not config.plugins.subsSupport.dvb.fpsDriftEnable.value:
            return 1.0

        videoFps = getFps(self.session, True)
        if videoFps is None:
            return 1.0

        cfg = dict(FPS_RATIO_SETTINGS).get("%.3f" % float(videoFps))
        return self._safeRatio(cfg, 1.0) if cfg else 1.0

    def setRefTime(self):
        self.reftime = time.time() * 1000
        self.refposition = self.position
        self.delay = 0

    def isPaused(self):
        return self.paused

    def start(self):
        self.fpsRatio = self.subsFpsRatio * self.getFpsDriftOverride()
        self.renderer.show()
        self.resume()

    def pause(self):
        self.waitTimer.stop()
        self.hideTimer.stop()
        self.paused = True

    def resume(self):
        self.waitTimer.stop()
        self.hideTimer.stop()
        self.setRefTime()
        self.renderSub()
        self.paused = False
        self.startHideTimer()

    def renderSub(self):
        for f in self.onRenderSub:
            f(self.subsList[self.position])
        self.renderer.setSubtitle(self.subsList[self.position])

    def hideSub(self):
        for f in self.onHideSub:
            f(self.subsList[self.position])
        self.renderer.hideSubtitle()

    def startHideTimer(self):
        self.hideTimer.start(int(self.subsList[self.position]['duration'] * self.fpsRatio), True)

    def hideTimerCallback(self):
        self.hideTimer.stop()
        self.waitTimer.stop()
        if self.position == len(self.subsList) - 1:
            self.hideSub()
        elif self.subsList[self.position]['end'] * self.fpsRatio + (200 * 90) < self.subsList[self.position + 1]['start'] * self.fpsRatio:
            self.hideSub()

        if self.position < len(self.subsList) - 1:
            self.position += 1
            self.toTime = self.reftime + ((self.subsList[self.position]['start'] - self.subsList[self.refposition]['start']) / 90 * self.fpsRatio)
            timeout = ((self.subsList[self.position]['start'] - self.subsList[self.position - 1]['end']) / 90 * self.fpsRatio) + self.delay
            self.waitTimer.start(int(timeout), True)

    def doWait(self):
        timeNow = time.time() * 1000
        delay = int(self.toTime - timeNow)
        if delay > 50:
            self.waitTimer.start(delay, True)
        elif delay <= 50 and delay >= 0:
            print("[SubsEngineDVB] sub shown sooner by %s ms" % (delay))
            self.delay = 0
            self.waitTimer.stop()
            self.renderSub()
            self.startHideTimer()
        else:
            print("[SubsEngineDVB] sub shown later by %s ms" % (abs(delay)))
            self.delay = delay
            self.waitTimer.stop()
            self.renderSub()
            self.startHideTimer()

    def seekTo(self, time):
        self.waitTimer.stop()
        self.hideTimer.stop()
        print("[SubsEngineDVB] seekTo, position before seek: %d" % self.position)
        firstSub = self.subsList[0]
        lastSub = self.subsList[-1]
        position = self.position
        if time > lastSub['start'] / 90 * self.fpsRatio:
            position = self.subsList.index(lastSub)
        elif time < firstSub['start'] / 90 * self.fpsRatio:
            position = 0
        elif abs(time - (firstSub['start'] / 90 * self.fpsRatio)) < abs(time - (lastSub['start'] / 90 * self.fpsRatio)):
            position = 0
            subStartTime = firstSub['start'] / 90 * self.fpsRatio
            while time > subStartTime:
                position += 1
                subStartTime = self.subsList[position]['start'] / 90 * self.fpsRatio
        else:
            position = self.subsList.index(lastSub)
            subStartTime = lastSub['start'] / 90 * self.fpsRatio
            while time < subStartTime:
                position -= 1
                subStartTime = self.subsList[position]['start'] / 90 * self.fpsRatio
        self.position = position
        print("[SubsEngineDVB] seekTo, position after seek: %d" % (self.position))
        self.renderSub()
        if not self.paused:
            self.setRefTime()
            self.startHideTimer()

    def seekRelative(self, time):
        self.waitTimer.stop()
        self.hideTimer.stop()
        print("[SubsEngine] seekRelative, position before seek: %d" % self.position)
        startSubTime = self.subsList[self.position]['start'] / 90 * self.fpsRatio
        position = self.position
        if time > 0:
            nextStartSubTime = 0
            while position != len(self.subsList) - 1 and time > nextStartSubTime:
                position += 1
                nextStartSubTime = ((self.subsList[position]['start']) / 90 * self.fpsRatio) - startSubTime
        else:
            prevEndSubTime = 0
            while position != 0 and time < prevEndSubTime:
                position -= 1
                prevEndSubTime = (self.subsList[position]['end'] / 90 * self.fpsRatio) - startSubTime
        self.position = position
        print("[SubsEngine] seekRelative, position after seek: %d" % self.position)
        self.renderSub()
        if not self.paused:
            self.setRefTime()
            self.startHideTimer()

    def toNextSub(self):
        self.waitTimer.stop()
        self.hideTimer.stop()
        if self.renderer.subShown and self.position < len(self.subsList) - 1:
            self.position += 1
        self.renderSub()
        if not self.paused:
            self.setRefTime()
            self.startHideTimer()

    def toPrevSub(self):
        self.waitTimer.stop()
        self.hideTimer.stop()
        if self.position > 0:
            self.position -= 1
        self.renderSub()
        if not self.paused:
            self.setRefTime()
            self.startHideTimer()

    def toSub(self, position):
        self.waitTimer.stop()
        self.hideTimer.stop()
        self.position = position
        self.renderSub()
        if not self.paused:
            self.setRefTime()
            self.startHideTimer()

    def close(self):
        self.waitTimer.stop()
        del self.waitTimer_conn
        del self.waitTimer
        self.hideTimer.stop()
        del self.hideTimer_conn
        del self.hideTimer
