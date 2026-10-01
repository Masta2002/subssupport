# -*- coding: utf-8 -*-
"""Prijevodi-Online.org seeker (public JSON API of the 2026 site, no login)."""
import os
import re

import requests

from ..seeker import SubtitlesDownloadError, SubtitlesErrors
from ..utilities import languageTranslate, log

API_URL = 'https://www.prijevodi-online.org/api/v1/'
TIMEOUT = 20
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36',
           'Accept': 'application/json'}

# site language code -> ISO 639-1 ('cnr', 'mix' and '??' have no mapping and are skipped)
SITE_LANGS = {'bs': 'bs', 'hr': 'hr', 'sr': 'sr', 'sr-cyr': 'sr', 'mk': 'mk', 'en': 'en'}


def _get(path, **params):
    r = requests.get(API_URL + path, params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def _pick(items, name, year=None):
    """Prefer an exact (case-insensitive) title match, then the year."""
    name = name.strip().lower()
    exact = [i for i in items if name in ((i.get('title') or '').lower(), (i.get('originalTitle') or '').lower())]
    if year:
        dated = [i for i in exact or items if (i.get('releaseDate') or '')[:4] == str(year)]
        if dated:
            return dated[0]
    if exact:
        return exact[0]
    return items[0] if len(items) == 1 else None


def _episode_translations(tvshow, season, episode):
    series = _pick(_get('series', search=tvshow)['series']['items'], tvshow)
    if not series:
        log(__name__, 'series "%s" not found' % tvshow)
        return []
    episodes = _get('series/%d/episodes' % series['id'])['episodes']['items']
    ep = [e for e in episodes if e['seasonNumber'] == season and e['episodeNumber'] == episode]
    if not ep:
        log(__name__, '%s S%02dE%02d not found' % (series['title'], season, episode))
        return []
    items = _get('translations/series', episodeId=ep[0]['id'], perPage=100)['translations']['items']
    for item in items:
        item['kind'] = 'series'
        release = item.get('description') or item.get('name') or ''
        item['label'] = '%s S%02dE%02d %s' % (series['title'], season, episode, release)
    return items


def _movie_translations(title, year):
    movie = _pick(_get('movies', search=title)['movies']['items'], title, year)
    if not movie:
        log(__name__, 'movie "%s" not found' % title)
        return []
    items = _get('translations/movies', movieId=movie['id'], perPage=100)['movieTranslations']['items']
    for item in items:
        item['kind'] = 'movies'
        release = re.sub(r'(\.srt)?\.(zip|rar)$', '', item.get('title') or '', flags=re.I)
        item['label'] = '%s (%s) %s' % (movie['title'], (movie.get('releaseDate') or '')[:4], release or item.get('releaseFormatName') or '')
    return items


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):  # standard input
    codes = {languageTranslate(lang, 0, 2) for lang in (lang1, lang2, lang3)}
    if tvshow:
        if not (int(season or 0) and int(episode or 0)):
            return [], '', 'season and episode are required'
        items = _episode_translations(tvshow, int(season), int(episode))
    else:
        items = _movie_translations(title, year)

    subtitles_list = []
    for item in items:
        code = SITE_LANGS.get(item.get('languageCode'))
        if code not in codes:
            continue
        subtitles_list.append({'filename': ' '.join(item['label'].split()),
                               'language_name': languageTranslate(code, 2, 0),
                               'language_flag': code,
                               'ID': str(item['id']),
                               'kind': item['kind'],
                               'rating': '0',
                               'sync': False,
                               'hearing_imp': bool(item.get('hearingImpaired'))})
    log(__name__, 'found %d subtitles' % len(subtitles_list))
    return subtitles_list, '', ''  # standard output


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):  # standard input
    params = subtitles_list[pos]
    url = '%stranslations/%s/%s/download' % (API_URL, params['kind'], params['ID'])
    log(__name__, 'downloading %s' % url)
    r = requests.get(url, headers=dict(HEADERS, Accept='*/*'), timeout=TIMEOUT)
    if r.status_code in (401, 402, 403):
        raise SubtitlesDownloadError(SubtitlesErrors.NO_CREDENTIALS_ERROR,
                                     'Prijevodi-Online: this subtitle needs a logged-in account with tokens (HTTP %d)' % r.status_code)
    r.raise_for_status()
    if r.content[:2] == b'PK':
        ext = 'zip'
    elif r.content[:4] == b'Rar!':
        ext = 'rar'
    elif r.content.lstrip()[:1] in (b'<', b'{'):
        raise SubtitlesDownloadError(SubtitlesErrors.UNKNOWN_ERROR, 'Prijevodi-Online did not return a subtitle file')
    else:
        ext = 'srt'
    path = os.path.join(tmp_sub_dir, 'prijevodionline_%s.%s' % (params['ID'], ext))
    with open(path, 'wb') as f:
        f.write(r.content)
    return False, params['language_name'], path  # standard output
