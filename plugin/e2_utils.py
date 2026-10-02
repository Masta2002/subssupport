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
from io import BytesIO
import os
from urllib.parse import urlencode
from twisted.internet import reactor
from twisted.web.client import Agent, BrowserLikePolicyForHTTPS, BrowserLikeRedirectAgent, FileBodyProducer, PartialDownloadError, readBody
from twisted.web.http_headers import Headers
from xml.etree.ElementTree import parse as parse_xml
from Components.Label import Label
from Components.ConfigList import ConfigList
from Components.Sources.StaticText import StaticText
from Components.ActionMap import ActionMap
from Components.Language import language
from Components.Pixmap import Pixmap
from Components.Sources.Boolean import Boolean
from Components.Sources.List import List
from Components.ConfigList import ConfigListScreen
from Components.config import ConfigText, ConfigSubsection, ConfigDirectory, \
    ConfigYesNo, ConfigPassword, getConfigListEntry, configfile
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Tools.Directories import fileExists, SCOPE_SKIN, SCOPE_CURRENT_SKIN, resolveFilename
from enigma import addFont, eEnv, ePicLoad, getDesktop

from .compat import eConnectCallback
from Tools.LoadPixmap import LoadPixmap


HTTP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:138.0) Gecko/20100101 Firefox/138.0"


class HTTPError(Exception):
    def __init__(self, code, url):
        Exception.__init__(self, "HTTP %d: %s" % (code, url))
        self.code = code


def fetch(url, params=None, headers=None, data=None, timeout=15):
    """Non-blocking GET (POST when data is given) with twisted, returns a Deferred firing with the body (bytes)."""
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    allHeaders = {"User-Agent": HTTP_USER_AGENT, "Accept": "*/*"}
    allHeaders.update(headers or {})
    agent = BrowserLikeRedirectAgent(Agent(reactor, contextFactory=BrowserLikePolicyForHTTPS(), connectTimeout=timeout))
    body = None
    if data is not None:
        body = FileBodyProducer(BytesIO(data if isinstance(data, bytes) else data.encode("utf-8")))
    d = agent.request(b"GET" if body is None else b"POST", url.encode("utf-8"),
                      Headers(dict((k.encode("utf-8"), [v.encode("utf-8")]) for k, v in allHeaders.items())), body)

    def partial(failure):  # a body without Content-Length ends with a PartialDownloadError
        failure.trap(PartialDownloadError)
        return failure.value.response

    def gotResponse(response):
        def checkCode(content):
            if not 200 <= response.code < 300:
                raise HTTPError(response.code, url)
            return content
        return readBody(response).addErrback(partial).addCallback(checkCode)
    d.addCallback(gotResponse)
    d.addTimeout(timeout, reactor)
    return d


def downloadPage(url, filename, params=None, headers=None, timeout=15):
    """fetch() into a file, returns a Deferred firing with the filename."""
    def save(content):
        with open(filename, "wb") as f:
            f.write(content)
        return filename
    return fetch(url, params, headers, timeout=timeout).addCallback(save)


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


class CaptchaDialog(Screen):
    # shows the captcha picture above the image's own virtual keyboard, closes with the typed text (None on cancel)
    skin = """
        <screen name="SubsSupportCaptcha" position="center,40" size="560,130" flags="wfNoBorder" zPosition="99" resolution="1280,720">
            <widget name="captcha" position="10,10" size="540,110" alphatest="blend" />
        </screen>"""

    def __init__(self, session, captchaFile):
        Screen.__init__(self, session)
        self["captcha"] = Pixmap()
        self.captchaFile = captchaFile
        self.picLoad = ePicLoad()
        self.picLoad_conn = eConnectCallback(self.picLoad.PictureData, self.showPicture)
        self.onLayoutFinish.append(self.decodePicture)
        self.onShown.append(self.openKeyboard)
        self.onClose.append(self.__onClose)

    def decodePicture(self):
        size = self["captcha"].instance.size()
        self.picLoad.setPara([size.width(), size.height(), 1, 1, 0, 1, "#002C2C39"])
        self.picLoad.startDecode(self.captchaFile)

    def showPicture(self, picInfo=""):
        ptr = self.picLoad.getData()
        if ptr is not None:
            self["captcha"].instance.setPixmap(ptr)

    def openKeyboard(self):
        self.onShown.remove(self.openKeyboard)
        self.session.openWithCallback(self.close, VirtualKeyBoard, title=_("Type text of picture"))

    def __onClose(self):
        del self.picLoad_conn
        del self.picLoad


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

    fontExts = (".ttf", ".otf")
    fontDir = eEnv.resolve("${datadir}/fonts/")
    pluginFontDir = os.path.join(os.path.dirname(__file__), "fonts", "")
    print('[getFonts] fontDir: %s' % fontDir)
    allFonts = []
    for directory in (fontDir, pluginFontDir):
        if not os.path.isdir(directory):
            continue
        for font in os.listdir(directory):
            fontPath = os.path.join(directory, font)
            if os.path.isdir(fontPath):
                allFonts.extend(os.path.join(fontPath, f) for f in os.listdir(fontPath) if f.lower().endswith(fontExts))
            elif font.lower().endswith(fontExts):
                allFonts.append(fontPath)

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

    for fontFilepath in allFonts:
        fontFilename = os.path.basename(fontFilepath)
        fontName = os.path.splitext(fontFilename)[0]
        if fontFilepath.startswith(pluginFontDir):
            fontName = "SS_" + fontName  # plugin fonts, avoid clashes with system/skin fonts
        elif fontFilename in fonts:
            FONTS[fonts[fontFilename]] = fontFilename
            continue
        addFont(fontFilepath, fontName, 100, False)
        FONTS[fontName] = fontFilepath

    if "Regular" not in FONTS:
        FONTS["Regular"] = ""

    return FONTS.keys()


class BaseMenuScreen(Screen, ConfigListScreen):

    def __init__(self, session, title, on_change=None):
        Screen.__init__(self, session)
        ConfigListScreen.__init__(self, [], session=session, on_change=on_change)
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
