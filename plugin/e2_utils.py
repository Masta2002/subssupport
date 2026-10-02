# -*- coding: UTF-8 -*-
#################################################################################
#
#    This module is part of SubsSupport plugin
#    Coded by mx3L (c) 2014
#
#    This program is free software; you can redistribute it and/or
#    modify it under the terms of the GNU General Public License
#    as published by the Free Software Foundation; either version 2
#    of the License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#################################################################################
from . import _
import os
import shutil
import requests
from twisted.internet.threads import deferToThread
from xml.etree.ElementTree import parse as parse_xml
from Components.Label import Label
from Components.ConfigList import ConfigList
from Components.Sources.StaticText import StaticText
from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigList
from Components.Console import Console
from Components.Language import language
from Components.Pixmap import Pixmap
from Components.Sources.Boolean import Boolean
from Components.Sources.List import List
from Components.Sources.StaticText import StaticText
from Components.ConfigList import ConfigListScreen
from Components.config import ConfigText, ConfigSubsection, ConfigDirectory, \
    ConfigYesNo, ConfigPassword, getConfigListEntry, configfile
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.Directories import pathExists, fileExists, SCOPE_SKIN, SCOPE_CURRENT_SKIN, resolveFilename
from Components.ActionMap import NumberActionMap, ActionMap, HelpableActionMap
from Components.config import ConfigText, KEY_0, KEY_DELETE, KEY_BACKSPACE, config
from enigma import addFont, eEnv, ePicLoad, getDesktop, eListboxPythonMultiContent, eListbox, eTimer, gFont, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_HALIGN_CENTER, RT_WRAP, loadPNG

from .compat import eConnectCallback
from Tools.LoadPixmap import LoadPixmap


def downloadPage(url, filename, params=None, headers=None, cookies=None):
    return getPage(url, params, headers, cookies)


def getPage(url, params=None, headers=None, cookies=None, timeout=None):
    headers = headers or {}
    timeout = timeout or 30.05
    headers["user-agent"] = "Mozilla/5.0 Gecko/20100101 Firefox/100.0"
    return deferToThread(requests.get, url, params=params, headers=headers, cookies=cookies, timeout=timeout)

def getDesktopSize():
    s = getDesktop(0).size()
    return (s.width(), s.height())


def isFullHD():
    desktopSize = getDesktopSize()
    return desktopSize[0] == 1920


def LanguageEntryComponent(file, name, index):
    png = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, 'countries/' + index + '.png'))
    if png is None:
        png = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, 'countries/' + file + '.png'))
        if png is None:
            png = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, 'countries/missing.png'))
    res = (index, name, png)
    return res


class MyConfigList(ConfigList):
    def __init__(self, list, session, enabled=True):
        self.enabled = enabled
        ConfigList.__init__(self, list, session)

    def enableList(self):
        self.enabled = True
        self.instance.setSelectionEnable(True)
        self.selectionChanged()

    def disableList(self):
        self.instance.setSelectionEnable(False)
        if isinstance(self.current, tuple) and len(self.current) >= 2:
                self.current[1].onDeselect(self.session)
        self.enabled = False

    def selectionChanged(self):
        if self.enabled:
            return ConfigList.selectionChanged(self)

    def postWidgetCreate(self, instance):
        if not self.enabled:
            instance.setSelectionEnable(False)
        ConfigList.postWidgetCreate(self, instance)


class MyLanguageSelection(Screen):
    skin = """
    <screen name="MyLanguageSelection" position="center,center" size="380,400" title="Language selection" zPosition="3" resolution="1280,720">
        <widget source="languages" render="Listbox" position="0,0" size="380,400" scrollbarMode="showOnDemand">
            <convert type="TemplatedMultiContent">
                {"template": [
                        MultiContentEntryText(pos = (80, 10), size = (200, 50), flags = RT_HALIGN_LEFT, text = 1), # index 1 is the language name,
                        MultiContentEntryPixmap(pos = (10, 5), size = (60, 40), png = 2), # index 2 is the pixmap
                    ],
                 "fonts": [gFont("Regular", 20)],
                 "itemHeight": 50
                }
            </convert>
        </widget>
    </screen>
    """

    LANGUAGE_LIST = []

    def __init__(self, session, currentLanguage):
        Screen.__init__(self, session)
        self.oldActiveLanguage = currentLanguage
        self["languages"] = List([])
        self["actions"] = ActionMap(["OkCancelActions"],
        {
            "ok": self.save,
            "cancel": self.cancel,
        }, -1)
        self.updateList()
        self.onLayoutFinish.append(self.selectActiveLanguage)

    def selectActiveLanguage(self):
        self.setTitle(_("Language selection"))
        pos = 0
        for pos, x in enumerate(self['languages'].list):
            if x[0] == self.oldActiveLanguage:
                self["languages"].index = pos
                break

    def updateLanguageList(self):
        languageList = language.getLanguageList()
        languageCountryList = [x[0] for x in languageList]
        for lang in [("Arabic", "ar", "AE"),
                ("Български", "bg", "BG"),
                ("Català", "ca", "AD"),
                ("Česky", "cs", "CZ"),
                ("Dansk", "da", "DK"),
                ("Deutsch", "de", "DE"),
                ("Ελληνικά", "el", "GR"),
                ("English", "en", "EN"),
                ("Español", "es", "ES"),
                ("Eesti", "et", "EE"),
                ("Persian", "fa", "IR"),
                ("Suomi", "fi", "FI"),
                ("Français", "fr", "FR"),
                ("Frysk", "fy", "NL"),
                ("Hebrew", "he", "IL"),
                ("Hrvatski", "hr", "HR"),
                ("Bosanski", "bs", "BS"),
                ("Magyar", "hu", "HU"),
                ("Íslenska", "is", "IS"),
                ("Italiano", "it", "IT"),
                ("Kurdish", "ku", "KU"),
                ("Lietuvių", "lt", "LT"),
                ("Latviešu", "lv", "LV"),
                ("Nederlands", "nl", "NL"),
                ("Norsk Bokmål", "nb", "NO"),
                ("Norsk", "no", "NO"),
                ("Polski", "pl", "PL"),
                ("Português", "pt", "PT"),
                ("Português do Brasil", "pt", "BR"),
                ("Romanian", "ro", "RO"),
                ("Русский", "ru", "RU"),
                ("Slovensky", "sk", "SK"),
                ("Slovenščina", "sl", "SI"),
                ("Srpski", "sr", "YU"),
                ("Svenska", "sv", "SE"),
                ("ภาษาไทย", "th", "TH"),
                ("Türkçe", "tr", "TR"),
                ("Ukrainian", "uk", "UA")]:
            if str(lang[1] + "_" + lang[2]) not in languageCountryList:
                print('adding', lang)
                languageList.append((str(lang[1] + "_" + lang[2]), lang))
        MyLanguageSelection.LANGUAGE_LIST = languageList

    def getLanguageList(self):
        if len(MyLanguageSelection.LANGUAGE_LIST) == 0:
            self.updateLanguageList()
        return MyLanguageSelection.LANGUAGE_LIST

    def updateList(self):
        languageList = self.getLanguageList()
        if not languageList:  # no language available => display only english
            list = [LanguageEntryComponent("en", "English", "en_EN")]
        else:
            list = [LanguageEntryComponent(file=x[1][2].lower(), name=x[1][0], index=x[0]) for x in languageList]
        self["languages"].list = list

    def save(self):
        self.close(self['languages'].list[self['languages'].index][0][:2])

    def cancel(self):
        self.close()


class ConfigFinalText(ConfigText):
    def __init__(self, default="", visible_width=60):
        ConfigText.__init__(self, default, fixed_size=True, visible_width=visible_width)

    def handleKey(self, key, callback=None):
        pass

    def getValue(self):
        return ConfigText.getValue(self)

    def setValue(self, val):
        ConfigText.setValue(self, val)

    def getMulti(self, selected):
        return ConfigText.getMulti(self, selected)

    def onSelect(self, session):
        self.allmarked = (self.value != "")


class Captcha(object):
    def __init__(self, session, captchaCB, imagePath, destPath='/tmp/captcha.png'):
        self.session = session
        self.captchaCB = captchaCB
        self.destPath = destPath

        if os.path.isfile(imagePath):
            self.openCaptchaDialog(imagePath)
        else:
            downloadPage(imagePath, destPath).addCallback(self.downloadCaptchaSuccess).addErrback(self.downloadCaptchaError)

    def openCaptchaDialog(self, captchaPath):
        self.session.openWithCallback(self.captchaCB, CaptchaDialog, captchaPath)

    def downloadCaptchaSuccess(self, txt=""):
        print("[Captcha] downloaded successfully:")
        self.openCaptchaDialog(self.destPath)

    def downloadCaptchaError(self, err):
        print("[Captcha] download error:", err)
        self.captchaCB('')


class CaptchaDialog(VirtualKeyBoard):
    skin = """
    <screen name="CaptchDialog" position="center,center" size="560,485" zPosition="99" title="Virtual keyboard" resolution="1280,720">
        <ePixmap pixmap="skin_default/vkey_text.png" position="9,165" zPosition="-4" size="542,52" alphatest="on" />
        <widget source="country" render="Pixmap" position="490,0" size="60,40" alphatest="on" borderWidth="2" borderColor="yellow" >
            <convert type="ValueToPixmap">LanguageCode</convert>
        </widget>
        <widget name="header" position="10,10" size="500,20" font="Regular;20" transparent="1" noWrap="1" />
        <widget position="10,455" size="60,35" name="Green" pixmap="skin_default/buttons/key_green.png" zPosition="3"  alphatest="blend" />
        <eLabel text="Save" zPosition="3" position="50,450" size="120,35" font="Regular;20" transparent="1" backgroundColor="black" halign="center" valign="center" />
        <widget name="captcha" position="10, 50" size ="540,110" alphatest="blend" zPosition="-1" />
        <widget name="text" position="12,165" size="536,46" font="Regular;46" transparent="1" noWrap="1" halign="right" />
        <widget name="list" position="10,220" size="540,225" selectionDisabled="1" transparent="1" />
    </screen>
    """

    def __init__(self, session, captcha_file, **kwargs):
        VirtualKeyBoard.__init__(self, session, _('Type text of picture'))
        self["captcha"] = Pixmap()
        self['Password'] = Label()
        self['Green'] = Pixmap()
        self['key_green'] = StaticText(_('Save'))
        self["text"] = self['text']
        self["myActionMap"] = NumberActionMap(["WizardActions", "InputBoxActions", "ColorActions"], {
            "green": self.save
        }, -1)
        self.picPath = captcha_file
        self.picLoad = ePicLoad()
        self.picLoad_conn = eConnectCallback(self.picLoad.PictureData, self.decodePicture)
        self.onLayoutFinish.append(self.showPicture)
        self.onClose.append(self.__onClose)

    def showPicture(self):
        self.picLoad.setPara([self["captcha"].instance.size().width(), self["captcha"].instance.size().height(), 1, 1, 0, 1, "#002C2C39"])
        self.picLoad.startDecode(self.picPath)

    def decodePicture(self, PicInfo=""):
        ptr = self.picLoad.getData()
        self["captcha"].instance.setPixmap(ptr)

    def showPic(self, picInfo=""):
        ptr = self.picLoad.getData()
        if ptr is not None:
            self["captcha"].instance.setPixmap(ptr.__deref__())
            self["captcha"].show()

    def __onClose(self):
        del self.picLoad_conn
        del self.picLoad

    def save(self):
        Password = self['text'].getText()
        code = str(Password)
        #with open(LINKFILE, "a") as f: f.write(Password)
        Distnt = '/tmp/'
        Path = '/tmp/code'
        if pathExists(Distnt):
            Password = self['text'].getText()
            if Password != '':
                file = open(Path, 'w')
                file.write(Password.replace(' ', ''))
                file.close()


class DelayMessageBox(MessageBox):
    def __init__(self, session, seconds, message):
        MessageBox.__init__(self, session, message, type=MessageBox.TYPE_INFO, timeout=seconds, close_on_any_key=False, enable_input=False)
        self.skinName = "MessageBox"


def messageCB(text):
    print(text)


class E2SettingsProvider(dict):
    def __init__(self, providerName, configSubSection, defaults):
        providerName = providerName.replace('.', '_')
        self.__providerName = providerName
        setattr(configSubSection, providerName, ConfigSubsection())
        self.__rootConfigListEntry = getattr(configSubSection, providerName)
        self.__defaults = defaults
        self.createSettings()

    def __repr__(self):
        return '[E2SettingsProvider-%s]' % self.__providerName

    def __setitem__(self, key, value):
        self.setSetting(key, value)

    def __getitem__(self, key):
        return self.getSetting(key)

    def update(self, *args, **kwargs):
        if args:
            if len(args) > 1:
                raise TypeError("update expected at most 1 arguments, "
                                "got %d" % len(args))
            other = dict(args[0])
            for key in other:
                self[key] = other[key]
        for key in kwargs:
            self[key] = kwargs[key]

    def setdefault(self, key, value=None):
        if key not in self:
            self[key] = value
        return self[key]

    def getSettingsDict(self):
        return dict((key, self.getConfigEntry(key).value) for key in self.__defaults.keys())

    def createSettings(self):
        for name, value in self.__defaults.items():
            self.createConfigEntry(name, value['type'], value['default'])

    def createConfigEntry(self, name, type, default, *args, **kwargs):
        if type == 'text':
            setattr(self.__rootConfigListEntry, name, ConfigText(default=default, fixed_size=False))
        elif type == 'directory':
            setattr(self.__rootConfigListEntry, name, ConfigDirectory(default=default))
        elif type == 'yesno':
            setattr(self.__rootConfigListEntry, name, ConfigYesNo(default=default))
        elif type == 'password':
            setattr(self.__rootConfigListEntry, name, ConfigPassword(default=default))
        else:
            print(repr(self), 'cannot create entry of unknown type:', type)

    def getConfigEntry(self, key):
        try:
            return getattr(self.__rootConfigListEntry, key)
        except Exception:
            return None

    def getE2Settings(self):
        settingList = []
        sortList = self.__defaults.items()
        sortedList = sorted(sortList, key=lambda x: x[1]['pos'])
        for name, value in sortedList:
            settingList.append(getConfigListEntry(value['label'], self.getConfigEntry(name)))
        return settingList

    def getSetting(self, key):
        try:
            return self.getConfigEntry(key).value
        except Exception as e:
            print(repr(self), e, 'returning empty string for key:', key)
            return ""

    def setSetting(self, key, val):
        try:
            self.getConfigEntry(key).value = val
        except Exception as e:
            print(repr(self), e, 'cannot set setting:', key, ':', val)


class fps_float(float):
    def __eq__(self, other):
        return "%.3f" % self == "%.3f" % other

    def __str__(self):
        return "%.3f" % (self)


def getFps(session, validOnly=False):
    from enigma import iServiceInformation
    service = session.nav.getCurrentService()
    info = service and service.info()
    if not info:
        return None
    fps = info.getInfo(iServiceInformation.sFrameRate)
    if fps > 0:
        fps = fps_float("%.3f" % (fps / float(1000)))
        if validOnly:
            validFps = min([23.976, 23.98, 24.0, 25.0, 29.97, 30.0], key=lambda x: abs(x - fps))
            if fps != validFps and abs(fps - validFps) > 0.01:
                print("[getFps] unsupported fps: %.4f!" % (fps))
                return None
            return fps_float(validFps)
        return fps_float(fps)
    return None


FONTS = {}


def getFonts():
    global FONTS
    if len(FONTS) > 0:
        return FONTS.keys()

    allFonts = []

    # 1) System fonts (existing logic)
    fontDir = eEnv.resolve("${datadir}/fonts/")
    print('[getFonts] fontDir: %s' % fontDir)

    if os.path.isdir(fontDir):
        for font in os.listdir(fontDir):
            fontPath = os.path.join(fontDir, font)
            if os.path.isdir(fontPath):
                for f in os.listdir(fontPath):
                    if f.lower().endswith(".ttf"):
                        allFonts.append(os.path.join(fontPath, f))
            elif fontPath.lower().endswith(".ttf"):
                allFonts.append(fontPath)

    # 2) Plugin fonts (SubsSupport only) -> register with prefix to avoid clashes
    pluginFontDir = os.path.join(os.path.dirname(__file__), "fonts", "")
    if os.path.isdir(pluginFontDir):
        for f in os.listdir(pluginFontDir):
            if f.lower().endswith((".ttf", ".otf")):
                allFonts.append(os.path.join(pluginFontDir, f))

    # Skin font name mapping (existing logic)
    skinFiles = ["skin_default.xml", "skin_subtitles.xml", "skin_user.xml"]
    fonts = {}
    for skinFile in skinFiles:
        skinPath = resolveFilename(SCOPE_SKIN, skinFile)
        if fileExists(skinPath):
            try:
                skin = parse_xml(skinPath).getroot()
            except Exception as e:
                print(e)
                continue
            for c in skin.findall("fonts"):
                for font in c.findall("font"):
                    get_attr = font.attrib.get
                    filename = get_attr("filename", "")
                    name = get_attr("name", "Regular")
                    fonts[filename] = name
                    print('[getFonts] find font %s in %s' % (name, skinFile))

    # Register fonts
    for fontFilepath in allFonts:
        fontFilename = os.path.basename(fontFilepath)

        # If font comes from plugin folder -> force prefixed name
        if fontFilepath.startswith(pluginFontDir):
            base = os.path.splitext(fontFilename)[0]
            fontName = "SS_" + base
            addFont(fontFilepath, fontName, 100, False)
            FONTS[fontName] = fontFilepath
            continue

        # Existing behavior for system fonts
        if fontFilename not in fonts.keys():
            fontName = os.path.splitext(fontFilename)[0]
            addFont(fontFilepath, fontName, 100, False)
            FONTS[fontName] = fontFilepath
        else:
            FONTS[fonts[fontFilename]] = fontFilename

    if "Regular" not in FONTS:
        FONTS["Regular"] = ""

    return FONTS.keys()


class BaseMenuScreen(Screen, ConfigListScreen):

    def __init__(self, session, title):
        Screen.__init__(self, session)
        ConfigListScreen.__init__(self, [], session=session)
        self.skinName = "Setup"
        self["actions"] = ActionMap(["SetupActions", "ColorActions"],
            {
                "cancel": self.keyCancel,
                "green": self.keySave,
                "red": self.keyCancel,
                "blue": self.resetDefaults,
            }, -2)

        self["key_green"] = StaticText(_("Save"))
        self["key_red"] = StaticText(_("Cancel"))
        self["key_blue"] = StaticText(_("Reset Defaults"))
        self["key_yellow"] = StaticText("")
        self["VKeyIcon"] = Boolean(False)
        self["HelpWindow"] = Pixmap()
        self["HelpWindow"].hide()
        self["footnote"] = Label()
        self["description"] = Label()
        self.setTitle(title)
        self.onLayoutFinish.append(self.buildMenu)

    def buildMenu(self):
        pass

    def resetDefaults(self):
        for x in self["config"].list:
            x[1].value = x[1].default
        self.buildMenu()

    def keySave(self):
        for x in self["config"].list:
            x[1].save()
        configfile.save()
        self.close(True)

    def keyCancel(self):
        for x in self["config"].list:
            x[1].cancel()
        self.close()
