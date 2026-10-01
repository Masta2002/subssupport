# -*- coding: utf-8 -*-
"""Titulky.com seeker (Czech/Slovak).

Search is public. Download works anonymously until the daily per-IP limit is
reached, then titulky.com asks for a captcha (handed to captcha_cb). Logged-in
users (Titulkyuser/Titulkypass) get a higher limit.
"""
import os
import re
import time
from urllib.parse import urljoin

import requests

from ..seeker import SubtitlesDownloadError, SubtitlesErrors
from ..utilities import languageTranslate, log

SERVER_URL = 'https://www.titulky.com/'
TIMEOUT = 20

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'}

# set by XBMCSubtitlesAdapter
settings_provider = None
captcha_cb = None
delay_cb = None

LANGS = {'CZ': 'cs', 'SK': 'sk'}

ROW_RE = re.compile(r'<tr class="r[^"]*">(.*?)</tr>', re.S | re.I)
CELL_RE = re.compile(r'<td[^>]*>(.*?)</td>', re.S | re.I)
TAG_RE = re.compile(r'<[^>]+>')


def _text(html):
    return ' '.join(TAG_RE.sub(' ', html).replace('&nbsp;', ' ').split())


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
            'release': release.group(1).strip() if release else '',
            'episode': _text(cells[2]),
            'year': _text(cells[3]),
            'downloads': int(downloads) if downloads.isdigit() else 0,
            'lang': lang.group(1).upper()}


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):  # standard input
    codes = {languageTranslate(lang, 0, 2) for lang in (lang1, lang2, lang3)}
    if tvshow:
        query = '%s S%02dE%02d' % (tvshow, int(season or 0), int(episode or 0))
    else:
        # filter titles like <Localized movie name> (<Movie name>)
        query = title.split('(')[0].strip()
    log(__name__, 'searching for "%s"' % query)
    r = requests.get(SERVER_URL + 'index.php', params={'Fulltext': query, 'FindUser': ''}, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()

    file_name = os.path.basename(file_original_path or '').lower()
    subtitles_list = []
    for row in ROW_RE.findall(r.text):
        item = _parse_row(row)
        if not item:
            continue
        code = LANGS.get(item['lang'])
        if code not in codes:
            continue
        if year and not tvshow and item['year'] and item['year'] != str(year):
            continue
        if tvshow and item['episode'].upper() != query[-6:].upper():
            continue
        release = item['release']
        item.update({'filename': '%s %s' % (item['title'], release) if release else item['title'],
                     'language_name': languageTranslate(code, 2, 0),
                     'language_flag': code,
                     'sync': bool(release and file_name and release.lower() in file_name)})
        subtitles_list.append(item)
    max_downloads = max([s['downloads'] for s in subtitles_list] + [1])
    for sub in subtitles_list:
        sub['rating'] = str(sub['downloads'] * 10 // max_downloads)
    log(__name__, 'found %d subtitles' % len(subtitles_list))
    return subtitles_list, '', ''  # standard output


def _login(session, username, password):
    log(__name__, 'logging in as %s' % username)
    r = session.post(SERVER_URL + 'index.php', data={'Login': username, 'Password': password, 'foreverlog': '0', 'Detail2': ''},
                     timeout=TIMEOUT)
    r.raise_for_status()
    if 'BadLogin' in r.text or not session.cookies.get('LogonLogin'):
        raise SubtitlesDownloadError(SubtitlesErrors.INVALID_CREDENTIALS_ERROR,
                                     'Login to Titulky.com failed, check username/password in the provider settings')


def _solve_captcha(session, subtitle_id, tmp_sub_dir):
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


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):  # standard input
    params = subtitles_list[pos]
    subtitle_id = params['ID']
    session = requests.Session()
    session.headers.update(HEADERS)
    username = settings_provider.getSetting('Titulkyuser')
    password = settings_provider.getSetting('Titulkypass')
    if username and password:
        _login(session, username, password)

    r = session.get(SERVER_URL + 'idown.php', params={'R': str(int(time.time())), 'titulky': subtitle_id, 'histstamp': '', 'zip': 'z'},
                    timeout=TIMEOUT)
    r.raise_for_status()
    content = r.text
    if 'captcha/captcha.php' in content:
        content = _solve_captcha(session, subtitle_id, tmp_sub_dir)
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

    r = session.get(urljoin(SERVER_URL, link.group(1).replace('&amp;', '&')), timeout=TIMEOUT)
    r.raise_for_status()
    if r.content[:2] == b'PK':
        ext = 'zip'
    elif r.content[:4] == b'Rar!':
        ext = 'rar'
    elif r.content.lstrip()[:1] == b'<':
        raise SubtitlesDownloadError(SubtitlesErrors.UNKNOWN_ERROR, 'Titulky.com did not return a subtitle file')
    else:
        ext = 'srt'
    path = os.path.join(tmp_sub_dir, 'titulky_%s.%s' % (subtitle_id, ext))
    with open(path, 'wb') as f:
        f.write(r.content)
    return False, params['language_name'], path  # standard output
