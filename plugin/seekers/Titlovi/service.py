# -*- coding: utf-8 -*-
"""Titlovi.com seeker using the official Kodi API (account required).

Search: https://kodi.titlovi.com/api/subtitles/search (token from /gettoken)
Download: https://titlovi.com/download/?type=<Type>&mediaid=<Id> (no login)
"""
import time

from ..seeker import SubtitlesErrors, SubtitlesSearchError
from ..utilities import createSession, languageTranslate, log, saveSubtitle, wantedLanguages, yearMatch

API_URL = 'https://kodi.titlovi.com/api/subtitles'
DOWNLOAD_URL = 'https://titlovi.com/download/?type=%s&mediaid=%s'
TIMEOUT = 20

# set by XBMCSubtitlesAdapter
settings_provider = None

# ISO 639-1 -> language names used by the Titlovi API (search 'lang' and result 'Lang')
LANGS = {'bs': 'Bosanski', 'hr': 'Hrvatski', 'en': 'English', 'mk': 'Makedonski', 'sr': 'Srpski', 'sl': 'Slovenski'}
LANGS_REV = dict((v, k) for k, v in LANGS.items())
LANGS_REV['Engleski'] = 'en'

session = createSession('https://titlovi.com/')
# username -> (token, user_id, renew timestamp)
_token_cache = {}


def _credentials():
    username = (settings_provider.getSetting('username') or '').strip()
    password = settings_provider.getSetting('password') or ''
    if not username or not password:
        raise SubtitlesSearchError(SubtitlesErrors.NO_CREDENTIALS_ERROR,
                                   'Titlovi.com search needs a titlovi.com username and password (provider settings)')
    return username, password


def _login(username, password, force=False):
    cached = _token_cache.get(username)
    if cached and not force and cached[2] > time.time():
        return cached[0], cached[1]
    log(__name__, 'requesting new API token for %s' % username)
    r = session.post(API_URL + '/gettoken', params={'username': username, 'password': password, 'json': True},
                     timeout=TIMEOUT)
    if r.status_code == 401:
        _token_cache.pop(username, None)
        raise SubtitlesSearchError(SubtitlesErrors.INVALID_CREDENTIALS_ERROR, 'Titlovi.com login failed, check username/password')
    r.raise_for_status()
    data = r.json()
    # tokens live for days (ExpirationDate), renewing once a day is enough
    _token_cache[username] = (data['Token'], data['UserId'], time.time() + 24 * 3600)
    return data['Token'], data['UserId']


def _search_api(params):
    username, password = _credentials()
    for force in (False, True):  # a rejected token is renewed once
        token, user_id = _login(username, password, force)
        r = session.get(API_URL + '/search', params=dict(params, token=token, userid=user_id, json=True), timeout=TIMEOUT)
        if r.status_code != 401:
            break
        log(__name__, 'token rejected')
    r.raise_for_status()
    return r.json().get('SubtitleResults') or []


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    codes = [code for code in wantedLanguages(lang1, lang2, lang3) if code in LANGS]
    if not codes:
        return [], '', 'no supported language'

    params = {'lang': '|'.join(LANGS[c] for c in codes)}
    if tvshow:
        params['query'] = tvshow
        if int(season or 0) and int(episode or 0):
            params['season'] = int(season)
            params['episode'] = int(episode)
    else:
        params['query'] = title
    log(__name__, 'search params: %s' % params)
    return _parse_results(_search_api(params), codes, tvshow, year, params['query']), '', ''


def _parse_results(results, codes, tvshow, year, query):
    subtitles_list = []
    for item in results:
        code = LANGS_REV.get(item.get('Lang'))
        if code not in codes:
            continue
        item_year = str(item.get('Year') or '')
        if not tvshow and not yearMatch(item_year, year):
            continue
        name = item.get('Title') or query
        if tvshow and item.get('Season') and item.get('Episode'):
            name = '%s S%02dE%02d' % (name, int(item['Season']), int(item['Episode']))
        elif item_year:
            name = '%s (%s)' % (name, item_year)
        release = (item.get('Release') or '').strip()
        subtitles_list.append({'filename': '%s %s' % (name, release) if release else name,
                               'language_name': languageTranslate(code, 2, 0),
                               'ID': str(item['Id']),
                               'type': str(item.get('Type') or 1),
                               'sync': False})
    log(__name__, 'found %d subtitles' % len(subtitles_list))
    return subtitles_list


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    params = subtitles_list[pos]
    url = DOWNLOAD_URL % (params['type'], params['ID'])
    log(__name__, 'downloading %s' % url)
    r = session.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return False, params['language_name'], saveSubtitle(tmp_sub_dir, 'titlovi_%s' % params['ID'], r.content)
