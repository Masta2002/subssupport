'''
Created on Feb 10, 2014

@author: marko
'''
import os
from time import sleep

from .seeker import BaseSeeker
from .utilities import languageTranslate, allLang

from . import _


class XBMCSubtitlesAdapter(BaseSeeker):
    module = None

    def __init__(self, tmp_path, download_path, settings=None, settings_provider=None, captcha_cb=None, delay_cb=None, message_cb=None):
        assert self.module is not None, 'you have to provide xbmc-subtitles module'
        logo = os.path.join(os.path.dirname(self.module.__file__), 'logo.png')
        BaseSeeker.__init__(self, tmp_path, download_path, settings, settings_provider, logo)
        self.module.captcha_cb = captcha_cb
        self.module.delay_cb = delay_cb
        self.module.message_cb = message_cb
        # xbmc-subtitles module can use maximum of three different languages
        # we will fill default languages from supported langs  in case no languages
        # were provided. If provider has more than 3 supported languages this just
        # gets first three languages in supported_langs list, so most of the time its
        # best to pass languages which will be used for searching
        if len(self.supported_langs) == 1:
            self.lang1 = self.lang2 = self.lang3 = languageTranslate(self.supported_langs[0], 2, 0)
        elif len(self.supported_langs) == 2:
            self.lang1 = languageTranslate(self.supported_langs[0], 2, 0)
            self.lang2 = languageTranslate(self.supported_langs[1], 2, 0)
            self.lang3 = self.lang1
        else:
            self.lang1 = languageTranslate(self.supported_langs[0], 2, 0)
            self.lang2 = languageTranslate(self.supported_langs[1], 2, 0)
            self.lang3 = languageTranslate(self.supported_langs[2], 2, 0)

    # settings keys which must be filled in before searching (API keys)
    required_settings = ()

    def test_credentials(self):
        """Checks the configured credentials in a thread, returns a Deferred firing with a message."""
        from twisted.internet import threads

        def check():
            self.module.settings_provider = self.settings_provider
            return self.module.test_credentials()
        return threads.deferToThread(check)

    def show_message(self, session, message, is_error=False):
        from Screens.MessageBox import MessageBox
        session.open(MessageBox, message, MessageBox.TYPE_ERROR if is_error else MessageBox.TYPE_INFO, timeout=10)

    def _search(self, title, filepath, langs, season, episode, tvshow, year):
        missing = [self.default_settings[key]['label'] for key in self.required_settings if not self.settings_provider.getSetting(key).strip()]
        if missing:
            return {'list': [], 'session_id': "", 'msg': _("%s requires: %s") % (self.provider_name, ", ".join(missing))}
        file_original_path = filepath and filepath or ""
        title = title and title or file_original_path
        season = season if season else 0
        episode = episode if episode else 0
        tvshow = tvshow if tvshow else ""
        year = year if year else ""
        if len(langs) > 3:
            self.log.info('more then three languages provided, only first three will be selected')
        if len(langs) == 0:
            self.log.info('no languages provided will use default ones')
            lang1 = self.lang1
            lang2 = self.lang2
            lang3 = self.lang3
        elif len(langs) == 1:
            lang1 = lang2 = lang3 = languageTranslate(langs[0], 2, 0)
        elif len(langs) == 2:
            lang1 = lang3 = languageTranslate(langs[0], 2, 0)
            lang2 = languageTranslate(langs[1], 2, 0)
        elif len(langs) == 3:
            lang1 = languageTranslate(langs[0], 2, 0)
            lang2 = languageTranslate(langs[1], 2, 0)
            lang3 = languageTranslate(langs[2], 2, 0)
        self.log.info('using langs %s %s %s' % (lang1, lang2, lang3))
        self.module.settings_provider = self.settings_provider
        # Standard output -
        # subtitles list
        # session id (e.g a cookie string, passed on to download_subtitles),
        # message to print back to the user
        # return subtitlesList, "", msg
        subtitles_list, session_id, msg = self.module.search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp=False, rar=False, lang1=lang1, lang2=lang2, lang3=lang3, stack=None)
        return {'list': subtitles_list, 'session_id': session_id, 'msg': msg}

    def _download(self, subtitles, selected_subtitle, path=None):
        subtitles_list = subtitles['list']
        session_id = subtitles['session_id']
        pos = subtitles_list.index(selected_subtitle)
        zip_subs = os.path.join(self.tmp_path, selected_subtitle['filename'])
        tmp_sub_dir = self.tmp_path
        if path is not None:
            sub_folder = path
        else:
            sub_folder = self.tmp_path
        self.module.settings_provider = self.settings_provider
        # Standard output -
        # True if the file is packed as zip: addon will automatically unpack it.
        # language of subtitles,
        # Name of subtitles file if not packed (or if we unpacked it ourselves)
        # return False, language, subs_file
        compressed, language, filepath = self.module.download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id)
        if compressed is not False:
            if compressed is True or compressed == "":
                compressed = "zip"
            else:
                compressed = filepath
            if not os.path.isfile(filepath):
                filepath = zip_subs
        else:
            if isinstance(sub_folder, bytes):
                sub_folder = sub_folder.decode()
            filepath = os.path.join(sub_folder, filepath)
        return compressed, language, filepath

    def close(self):
        try:
            del self.module.captcha_cb
            del self.module.message_cb
            del self.module.delay_cb
            del self.module.settings_provider
        except Exception:
            pass


try:
    from .Subtitlecat import subtitlecat
except ImportError as e:
    subtitlecat = e


class SubtitlecatSeeker(XBMCSubtitlesAdapter):
    id = 'subtitlecat'
    module = subtitlecat
    if isinstance(module, Exception):
        error, module = module, None
    provider_name = 'Subtitlecat'
    supported_langs = allLang()
    default_settings = {}


try:
    from .Ytssubs import ytssubs
except ImportError as e:
    ytssubs = e


class YtssubsSeeker(XBMCSubtitlesAdapter):
    id = 'ytssubs'
    module = ytssubs
    if isinstance(module, Exception):
        error, module = module, None
    provider_name = 'Ytssubs'
    supported_langs = allLang()
    default_settings = {}
    movie_search = True
    tvshow_search = False


try:
    from .Justsubtitles import justsubtitles
except ImportError as e:
    justsubtitles = e


class JustsubtitlesSeeker(XBMCSubtitlesAdapter):
    id = 'justsubtitles'
    module = justsubtitles
    if isinstance(module, Exception):
        error, module = module, None
    provider_name = 'JustSubtitles'
    supported_langs = ['en', 'ar', 'de', 'it', 'id', 'ja', 'ko']
    default_settings = {}
    movie_search = True
    tvshow_search = False


try:
    from .LocalDrive import localdrive
except ImportError as e:
    localdrive = e


class LocalDriveSeeker(XBMCSubtitlesAdapter):
    module = localdrive
    if isinstance(module, Exception):
        error, module = module, None
    id = 'localdrive'
    provider_name = 'LocalDrive'
    supported_langs = allLang()
    default_settings = {'LocalSearchPath': {'label': _("Search Path"), 'type': 'text', 'default': "/media/hdd/subs", 'pos': 0}}


try:
    from .Subf2m import subf2m
except ImportError as e:
    subf2m = e


class Subf2mSeeker(XBMCSubtitlesAdapter):
    id = 'subf2m'
    module = subf2m
    if isinstance(module, Exception):
        error, module = module, None
    provider_name = 'Subf2m'
    supported_langs = allLang()
    default_settings = {}


try:
    from .Sub_Scene_com import sub_scene_com
except ImportError as e:
    sub_scene_com = e


class Sub_Scene_comSeeker(XBMCSubtitlesAdapter):
    id = 'sub_scene_com'
    module = sub_scene_com
    if isinstance(module, Exception):
        error, module = module, None
    provider_name = 'Sub_Scene_com'
    supported_langs = allLang()
    default_settings = {}


try:
    from .Subsource import subsource
except ImportError as e:
    subsource = e


class SubsourceSeeker(XBMCSubtitlesAdapter):
    id = 'subsource'
    module = subsource
    if isinstance(module, Exception):
        error, module = module, None
    provider_name = 'Subsource'
    supported_langs = allLang()
    default_settings = {'SubSource_API_KEY': {'label': _("API key"), 'type': 'text', 'default': '', 'pos': 0}}
    required_settings = ('SubSource_API_KEY',)


try:
    from .OpenSubtitles2 import opensubtitles2
except ImportError as e:
    opensubtitles2 = e


class OpenSubtitles2Seeker(XBMCSubtitlesAdapter):
    module = opensubtitles2
    if isinstance(module, Exception):
        error, module = module, None
    id = 'opensubtitles.com'
    provider_name = 'OpenSubtitles.com'
    supported_langs = allLang()
    default_settings = {
        'OpenSubtitles_username': {'label': _("Username"), 'type': 'text', 'default': "", 'pos': 0},
        'OpenSubtitles_password': {'label': _("Password"), 'type': 'password', 'default': "", 'pos': 1},
        'OpenSubtitles_API_KEY': {'label': _("API key"), 'type': 'text', 'default': '', 'pos': 2}
    }
    required_settings = ('OpenSubtitles_API_KEY',)


try:
    from .Subdl import subdl
except ImportError as ie:
    subdl = ie


class SubdlSeeker(XBMCSubtitlesAdapter):
    module = subdl
    if isinstance(module, Exception):
        error, module = module, None
    id = 'subdl.com'
    provider_name = 'Subdl'
    supported_langs = allLang()
    default_settings = {'Subdl_API_KEY': {'label': _("API key"), 'type': 'text', 'default': '', 'pos': 0}}
    required_settings = ('Subdl_API_KEY',)


try:
    from .Wyzie import wyzie
except ImportError as e:
    wyzie = e


class WyzieSeeker(XBMCSubtitlesAdapter):
    module = wyzie
    if isinstance(module, Exception):
        error, module = module, None
    id = 'wyzie'
    provider_name = 'Wyzie Subs'
    supported_langs = allLang()
    default_settings = {'Wyzie_API_KEY': {'label': _("API key"), 'type': 'text', 'default': '', 'pos': 0}}
    required_settings = ('Wyzie_API_KEY',)


try:
    from .Subtitlesmora import subtitlesmora
except ImportError as e:
    subtitlesmora = e


class SubtitlesmoraSeeker(XBMCSubtitlesAdapter):
    module = subtitlesmora
    if isinstance(module, Exception):
        error, module = module, None
    id = 'archive.org'
    provider_name = 'Subtitlesmora'
    supported_langs = ['ar']
    default_settings = {}
    movie_search = True
    tvshow_search = True


try:
    from .Titlovi import titlovi
except ImportError as e:
    titlovi = e


class TitloviSeeker(XBMCSubtitlesAdapter):
    module = titlovi
    if isinstance(module, Exception):
        error, module = module, None
    id = 'titlovi'
    provider_name = 'Titlovi'
    supported_langs = ['bs', 'hr', 'en', 'mk', 'sr', 'sl']
    default_settings = {'username': {'label': _("Username"), 'type': 'text', 'default': "", 'pos': 0},
                        'password': {'label': _("Password"), 'type': 'password', 'default': "", 'pos': 1}}
    required_settings = ('username', 'password')
    movie_search = True
    tvshow_search = True


try:
    from .PrijevodiOnline import prijevodionline
except ImportError as e:
    prijevodionline = e


class PrijevodiOnlineSeeker(XBMCSubtitlesAdapter):
    module = prijevodionline
    if isinstance(module, Exception):
        error, module = module, None
    id = 'prijevodionline'
    provider_name = 'Prijevodi-Online'
    supported_langs = ['bs', 'hr', 'sr', 'mk', 'en']
    default_settings = {}
    movie_search = True
    tvshow_search = True


try:
    from .MySubs import mysubs
except ImportError as ie:
    mysubs = ie


class MySubsSeeker(XBMCSubtitlesAdapter):
    id = 'mysubs'
    module = mysubs
    if isinstance(module, Exception):
        error, module = module, None
    provider_name = 'Mysubs'
    supported_langs = allLang()
    default_settings = {}


try:
    from .Titulky import titulkycom
except ImportError as e:
    titulkycom = e


class TitulkyComSeeker(XBMCSubtitlesAdapter):
    module = titulkycom
    if isinstance(module, Exception):
        error, module = module, None
    id = 'titulky.com'
    provider_name = 'Titulky.com'
    supported_langs = ['sk', 'cs']
    default_settings = {'Titulkyuser': {'label': _("Username"), 'type': 'text', 'default': "", 'pos': 0},
                        'Titulkypass': {'label': _("Password"), 'type': 'password', 'default': "", 'pos': 1}, }


try:
    from .Moviesubtitles import moviesubtitles
except ImportError as e:
    moviesubtitles = e


class MoviesubtitlesSeeker(XBMCSubtitlesAdapter):
    id = 'moviesubtitles'
    module = moviesubtitles
    if isinstance(module, Exception):
        error, module = module, None
    provider_name = 'Moviesubtitles.org'
    default_settings = {}
    supported_langs = ['en', 'fr', 'de', 'es', 'it', 'pl', 'ru', 'uk', 'hu', 'tr', 'el', 'ar', 'pt-br']
    default_settings = {}
    movie_search = True
    tvshow_search = False


try:
    from .Indexsubtitle import indexsubtitle
except ImportError as e:
    indexsubtitle = e


class IndexsubtitleSeeker(XBMCSubtitlesAdapter):
    id = 'indexsubtitle'
    module = indexsubtitle
    if isinstance(module, Exception):
        error, module = module, None
    provider_name = 'Indexsubtitle.cc'
    supported_langs = allLang()
    default_settings = {}
