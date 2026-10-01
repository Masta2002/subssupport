# -*- coding: utf-8 -*-
# JustSubtitles (justsubtitles.com): TMDb movie search + Next.js server action; the files are subdl.com
# archives, fetched through the site's own /api/download proxy (dl.subdl.com answers 403 without an api key)
import json
import os
import re

import requests

from ..user_agents import get_random_ua
from ..utilities import languageTranslate, log

MAIN_URL = "https://www.justsubtitles.com"
SEARCH_URL = "https://search.justsubtitles.com/api/search"
TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

# languages the site offers (code shown on the page -> name it expects in the server action)
SITE_LANGS = {'en': 'English', 'ar': 'Arabic', 'de': 'German', 'it': 'Italian', 'id': 'Indonesian',
              'ja': 'Japanese', 'ko': 'Korean'}

session = requests.Session()
session.headers.update({'User-Agent': get_random_ua(), 'Referer': MAIN_URL + '/'})
_action_ids = {}  # page chunk url -> "findSubsForLang" server action id (changes with every site deployment)


def normalize(title):
    return re.sub(r'[^a-z0-9]+', ' ', (title or '').lower()).strip()


def find_movie(title, year):
    """Returns (tmdb_id, year) of the best matching movie or (None, None)."""
    r = session.get(SEARCH_URL, params={'q': title}, timeout=TIMEOUT)
    r.raise_for_status()
    wanted, candidates = normalize(title), []
    for movie in r.json().get('results') or []:
        found = (movie.get('id'), (movie.get('release_date') or '')[:4])
        names = (normalize(movie.get('title')), normalize(movie.get('original_title')))
        match = 2 if wanted in names else any(wanted in name for name in names)
        if match:
            candidates.append((match * 2 + (found[1] == str(year)), found))
    candidates.sort(key=lambda c: -c[0])
    return candidates[0][1] if candidates else (None, None)


def get_action_id(tmdb_id):
    page = session.get('%s/movie/%s/x' % (MAIN_URL, tmdb_id), timeout=TIMEOUT)
    page.raise_for_status()
    chunk = re.search(r'/_next/static/chunks/app/movie/[^"\']+\.js', page.text)
    if not chunk:
        raise Exception('justsubtitles: movie page script not found')
    chunk = chunk.group(0)
    if chunk not in _action_ids:
        js = session.get(MAIN_URL + chunk, timeout=TIMEOUT)
        js.raise_for_status()
        m = re.search(r'createServerReference\)\("([0-9a-f]+)"', js.text)
        if not m:
            raise Exception('justsubtitles: server action id not found')
        _action_ids[chunk] = m.group(1)
    return _action_ids[chunk]


def find_subs(action_id, tmdb_id, code, year):
    """Calls the site's findSubsForLang server action, returns the list of subtitle dicts."""
    body = json.dumps([str(tmdb_id), {'code': code.upper(), 'language': SITE_LANGS[code]}, year or ''])
    r = session.post(MAIN_URL + '/', data=body, timeout=TIMEOUT, headers={
        'Accept': 'text/x-component', 'Content-Type': 'text/plain;charset=UTF-8', 'Next-Action': action_id,
        'Origin': MAIN_URL})
    r.raise_for_status()
    m = re.search(r'(?m)^1:', r.text)  # RSC row 1 holds the action result
    if not m:
        return []
    data = json.JSONDecoder(strict=False).raw_decode(r.text, m.end())[0]
    return (data.get('subtitles') or []) if isinstance(data, dict) else []


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    if tvshow:  # the site only lists movies
        return [], "", ""
    codes = []
    for lang in (lang1, lang2, lang3):
        code = languageTranslate(lang, 0, 2)
        if code in SITE_LANGS and code not in codes:
            codes.append(code)
    if not codes or not title:
        return [], "", ""
    tmdb_id, found_year = find_movie(title, year)
    log(__name__, "search '%s' (%s) -> tmdb %s" % (title, year, tmdb_id))
    if not tmdb_id:
        return [], "", ""
    action_id = get_action_id(tmdb_id)
    year = found_year or year or ''
    video = normalize(os.path.splitext(os.path.basename(file_original_path or ''))[0])
    subtitles_list = []
    for code in codes:
        for sub in find_subs(action_id, tmdb_id, code, year):
            if not sub.get('url'):
                continue
            name = sub.get('release_name') or sub.get('name') or title
            # old ".rar" entries answer 404/502, subdl serves every upload as ".zip" now
            url = re.sub(r'\.rar$', '.zip', sub['url'].split('?')[0])
            subtitles_list.append({'filename': name, 'language_name': languageTranslate(code, 2, 0),
                                   'sync': bool(video) and normalize(name) == video,
                                   'url': url, 'movie': title, 'year': year, 'tmdb_id': tmdb_id})
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    log(__name__, "downloading %s" % sub['url'])
    r = session.get(MAIN_URL + '/api/download', timeout=DOWNLOAD_TIMEOUT, params={
        'url': sub['url'], 'moviename': sub['movie'], 'year': sub['year'], 'backdrop': '', 'movieId': sub['tmdb_id']})
    r.raise_for_status()
    if not r.content or r.content.lstrip()[:1] == b'<':
        raise Exception('justsubtitles: download returned no subtitle file')
    if not os.path.isdir(tmp_sub_dir):
        os.makedirs(tmp_sub_dir)
    name = os.path.splitext(os.path.basename(sub['url']))[0] or 'subtitle'
    filepath = os.path.join(tmp_sub_dir, name + ('.rar' if r.content[:4] == b'Rar!' else '.zip'))
    with open(filepath, 'wb') as f:
        f.write(r.content)
    return False, sub['language_name'], filepath
