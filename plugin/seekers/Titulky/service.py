# -*- coding: utf-8 -*-
"""Titulky.com seeker (Czech/Slovak).

Search is public. Download works anonymously until the daily per-IP limit is
reached, then titulky.com asks for a captcha (handed to captcha_cb). Logged-in
users (Titulkyuser/Titulkypass) get a higher limit.
"""
import html
import os
import re
import time
from urllib.parse import urljoin

from ..seeker import SubtitlesDownloadError, SubtitlesErrors
from ..utilities import createSession, languageTranslate, log, saveSubtitle, wantedLanguages, yearMatch

SERVER_URL = 'https://www.titulky.com/'
TIMEOUT = 20

# set by XBMCSubtitlesAdapter
settings_provider = None
captcha_cb = None
delay_cb = None

LANGS = {'CZ': 'cs', 'SK': 'sk'}

ROW_RE = re.compile(r'<tr class="r[^"]*">(.*?)</tr>', re.S | re.I)
CELL_RE = re.compile(r'<td[^>]*>(.*?)</td>', re.S | re.I)
TAG_RE = re.compile(r'<[^>]+>')

session = createSession()
_logged_in = None  # (username, password) of the session login


def _text(cell):
    return ' '.join(html.unescape(TAG_RE.sub(' ', cell)).split())


def _parse_row(row):
    cells = CELL_RE.findall(row)
    if len(cells) < 6:
        return None
    link = re.search(r'href="[^"]*?-(\d+)\.htm"', cells[0])
    lang = re.search(r'alt="(\w+)"', cells[5])
    if not link or not lang:
        return None
    release = re.search(r'title="([^"]*)"', cells[1])
    downloads = _text(cells[4])
    return {'ID': link.group(1),
            'title': _text(cells[0]),
            'release': html.unescape(release.group(1)).strip() if release else '',
            'episode': _text(cells[2]),
            'year': _text(cells[3]),
            'downloads': int(downloads) if downloads.isdigit() else 0,
            'lang': lang.group(1).upper()}


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = wantedLanguages(lang1, lang2, lang3)
    if tvshow:
        tag = 'S%02dE%02d' % (int(season or 0), int(episode or 0))
        query = '%s %s' % (tvshow, tag)
    else:
        # filter titles like <Localized movie name> (<Movie name>)
        query = title.split('(')[0].strip()
    log(__name__, 'searching for "%s"' % query)
    r = session.get(SERVER_URL + 'index.php', params={'Fulltext': query, 'FindUser': ''}, timeout=TIMEOUT)
    r.raise_for_status()

    file_name = os.path.basename(file_original_path or '').lower()
    subtitles_list = []
    for row in ROW_RE.findall(r.text):
        item = _parse_row(row)
        if not item:
            continue
        code = LANGS.get(item['lang'])
        if code not in wanted:
            continue
        if not tvshow and not yearMatch(item['year'], year):
            continue
        if tvshow and item['episode'].upper() != tag:
            continue
        release = item['release']
        item.update({'filename': '%s %s' % (item['title'], release) if release else item['title'],
                     'language_name': languageTranslate(code, 2, 0),
                     'sync': bool(release and file_name and release.lower() in file_name)})
        subtitles_list.append(item)
    subtitles_list.sort(key=lambda s: (not s['sync'], -s['downloads']))
    log(__name__, 'found %d subtitles' % len(subtitles_list))
    return subtitles_list, '', ''


def _login():
    """Logs the session in once when username/password are set."""
    global _logged_in
    username = settings_provider.getSetting('Titulkyuser')
    password = settings_provider.getSetting('Titulkypass')
    if not username or not password or _logged_in == (username, password) and session.cookies.get('LogonLogin'):
        return
    log(__name__, 'logging in as %s' % username)
    _logged_in = None
    r = session.post(SERVER_URL + 'index.php', data={'Login': username, 'Password': password, 'foreverlog': '0', 'Detail2': ''},
                     timeout=TIMEOUT)
    r.raise_for_status()
    if 'BadLogin' in r.text or not session.cookies.get('LogonLogin'):
        raise SubtitlesDownloadError(SubtitlesErrors.INVALID_CREDENTIALS_ERROR,
                                     'Login to Titulky.com failed, check username/password in the provider settings')
    _logged_in = (username, password)


def _solve_captcha(subtitle_id, tmp_sub_dir):
    if not callable(captcha_cb):
        raise SubtitlesDownloadError(SubtitlesErrors.CAPTCHA_RETYPE_ERROR, 'Titulky.com daily limit reached, captcha required')
    log(__name__, 'daily limit reached, asking user for captcha')
    img = session.get(SERVER_URL + 'captcha/captcha.php', timeout=TIMEOUT)
    img.raise_for_status()
    img_path = os.path.join(tmp_sub_dir, 'titulky_captcha.jpg')
    with open(img_path, 'wb') as f:
        f.write(img.content)
    solution = captcha_cb(img_path)
    if not solution:
        raise SubtitlesDownloadError(SubtitlesErrors.CAPTCHA_RETYPE_ERROR, 'Captcha was not entered')
    r = session.post(SERVER_URL + 'idown.php', data={'downkod': solution, 'securedown': '2', 'zip': 'z', 'T': '',
                                                    'titulky': subtitle_id, 'histstamp': ''}, timeout=TIMEOUT)
    r.raise_for_status()
    if 'captcha/captcha.php' in r.text:
        raise SubtitlesDownloadError(SubtitlesErrors.CAPTCHA_RETYPE_ERROR, 'Invalid captcha text')
    return r.text


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    params = subtitles_list[pos]
    subtitle_id = params['ID']
    _login()
    r = session.get(SERVER_URL + 'idown.php', params={'R': str(int(time.time())), 'titulky': subtitle_id, 'histstamp': '', 'zip': 'z'},
                    timeout=TIMEOUT)
    r.raise_for_status()
    content = r.text
    if 'captcha/captcha.php' in content:
        content = _solve_captcha(subtitle_id, tmp_sub_dir)
    if 'CHYBA' in content:
        raise SubtitlesDownloadError(SubtitlesErrors.NO_CREDENTIALS_ERROR, 'Titulky.com refused the download, login required')
    link = re.search(r'id="downlink"\s+href="([^"]+)"', content) or re.search(r'href="([^"]+)"[^>]*id="downlink"', content)
    if not link:
        raise SubtitlesDownloadError(SubtitlesErrors.UNKNOWN_ERROR, 'Titulky.com download link not found')
    wait = re.search(r'CountDown\((\d+)\)', content)
    wait = int(wait.group(1)) if wait else 0
    if wait:
        log(__name__, 'waiting %d seconds before download' % wait)
        if callable(delay_cb):
            delay_cb(wait + 2)
        else:
            time.sleep(wait + 1)

    r = session.get(urljoin(SERVER_URL, html.unescape(link.group(1))), timeout=TIMEOUT)
    r.raise_for_status()
    return False, params['language_name'], saveSubtitle(tmp_sub_dir, 'titulky_%s' % subtitle_id, r.content)
