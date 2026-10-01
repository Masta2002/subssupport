# -*- coding: utf-8 -*-
# JustSubtitles (justsubtitles.com): TMDb movie search + Next.js server action; the files are subdl.com
# archives, fetched through the site's own /api/download proxy (dl.subdl.com answers 403 without an api key)
import json
import os
import re

from ..utilities import createSession, log, matchTitle, normalizeTitle, saveSubtitle, stripYear, wantedLanguages

MAIN_URL = "https://www.justsubtitles.com"
SEARCH_URL = "https://search.justsubtitles.com/api/search"
TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

# languages the site offers (code shown on the page -> name it expects in the server action)
SITE_LANGS = {'en': 'English', 'ar': 'Arabic', 'de': 'German', 'it': 'Italian', 'id': 'Indonesian',
              'ja': 'Japanese', 'ko': 'Korean'}

session = createSession(MAIN_URL + '/')
_action_ids = {}  # page chunk url -> "findSubsForLang" server action id (changes with every site deployment)


def find_movie(title, year):
    """Returns (tmdb_id, year) of the best matching movie or (None, None)."""
    r = session.get(SEARCH_URL, params={'q': title}, timeout=TIMEOUT)
    r.raise_for_status()
    results = []
    for movie in r.json().get('results') or []:
        found = (movie.get('id'), (movie.get('release_date') or '')[:4])
        results += [(movie.get('title'), found[1], found), (movie.get('original_title'), found[1], found)]
    return matchTitle(title, year, results) or (None, None)


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
    wanted = dict((code, name) for code, name in wantedLanguages(lang1, lang2, lang3).items() if code in SITE_LANGS)
    title = stripYear(title)
    if not wanted or not title:
        return [], "", ""
    tmdb_id, found_year = find_movie(title, year)
    log(__name__, "search '%s' (%s) -> tmdb %s" % (title, year, tmdb_id))
    if not tmdb_id:
        return [], "", ""
    action_id = get_action_id(tmdb_id)
    year = found_year or year or ''
    video = normalizeTitle(os.path.splitext(os.path.basename(file_original_path or ''))[0])
    subtitles_list = []
    for code, lang in wanted.items():
        for sub in find_subs(action_id, tmdb_id, code, year):
            if not sub.get('url'):
                continue
            name = sub.get('release_name') or sub.get('name') or title
            # old ".rar" entries answer 404/502, subdl serves every upload as ".zip" now
            url = re.sub(r'\.rar$', '.zip', sub['url'].split('?')[0])
            subtitles_list.append({'filename': name, 'language_name': lang,
                                   'sync': bool(video) and normalizeTitle(name) == video,
                                   'url': url, 'movie': title, 'year': year, 'tmdb_id': tmdb_id})
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    log(__name__, "downloading %s" % sub['url'])
    r = session.get(MAIN_URL + '/api/download', timeout=DOWNLOAD_TIMEOUT, params={
        'url': sub['url'], 'moviename': sub['movie'], 'year': sub['year'], 'backdrop': '', 'movieId': sub['tmdb_id']})
    r.raise_for_status()
    name = os.path.splitext(os.path.basename(sub['url']))[0] or 'subtitle'
    return False, sub['language_name'], saveSubtitle(tmp_sub_dir, name, r.content)
