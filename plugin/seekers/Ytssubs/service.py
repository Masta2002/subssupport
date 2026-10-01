# -*- coding: utf-8 -*-
import os
import re

import requests
from bs4 import BeautifulSoup

from ..user_agents import get_random_ua
from ..utilities import languageTranslate, log

MAIN_URL = "https://yifysubtitles.ch"
SEARCH_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

# site language names (normalized) that languageTranslate() does not know
LANG_ALIASES = {
    'farsi persian': 'fa', 'brazilian portuguese': 'pt-br', 'brazillian portuguese': 'pt-br',
    'portuguese brazilian': 'pt-br', 'chinese bg code': 'zh', 'chinese simplified': 'zh',
    'chinese traditional': 'zh', 'big 5 code': 'zh', 'spanish spain': 'es', 'spanish latin america': 'es',
}

session = requests.Session()
session.headers.update({'User-Agent': get_random_ua(), 'Referer': MAIN_URL + '/'})


def lang_code(name):
    """Language name (ours or the site's) -> ISO 639-1 code or None."""
    name = (name or '').strip()
    norm = re.sub(r'[^a-z]+', ' ', name.lower()).strip()
    code = LANG_ALIASES.get(norm) or languageTranslate(name, 0, 2) or languageTranslate(norm.title(), 0, 2)
    return 'pt-br' if code == 'pb' else code


def normalize_title(title):
    return re.sub(r'[^a-z0-9]+', ' ', (title or '').lower()).strip()


def find_movie(title, year):
    """Returns the IMDb id of the best matching search result or None."""
    r = session.get(MAIN_URL + '/ajax/search/', params={'mov': title}, timeout=SEARCH_TIMEOUT,
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    r.raise_for_status()
    wanted = normalize_title(title)
    exact, partial = [], []
    for item in r.json() or []:
        m = re.match(r'(.*?)\s+(\d{4})$', item.get('movie', '').strip())  # "The Matrix 1999"
        found, found_year = (m.group(1), m.group(2)) if m else (item.get('movie', ''), None)
        if normalize_title(found) == wanted:
            exact.append((found_year, item.get('imdb')))
        elif wanted in normalize_title(found):
            partial.append((found_year, item.get('imdb')))
    if year:
        for found_year, imdb in exact + partial:
            if found_year == str(year):
                return imdb
    return exact[0][1] if exact else None


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    if tvshow:  # movies only
        return [], "", ""
    wanted = set(filter(None, (lang_code(lang) for lang in (lang1, lang2, lang3))))
    imdb = find_movie(title, year)
    log(__name__, "search '%s' (%s) -> %s" % (title, year, imdb))
    if not imdb:
        return [], "", ""
    r = session.get('%s/movie-imdb/%s' % (MAIN_URL, imdb), timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    subtitles_list = []
    for row in BeautifulSoup(r.text, 'html.parser').select('tr[data-id]'):
        lang = row.select_one('span.sub-lang')
        link = row.select_one('a[href^="/subtitles/"]')
        code = lang and lang_code(lang.get_text(strip=True))
        if not link or code not in wanted:
            continue
        names = [n for n in link.stripped_strings if n.lower() != 'subtitle']
        rating = row.select_one('td.rating-cell')
        rating = rating.get_text(strip=True) if rating else '0'
        subtitles_list.append({'filename': names[0] if names else title, 'language_name': languageTranslate(code, 2, 0),
                               'sync': False, 'rating': rating if rating.lstrip('-').isdigit() else '0',
                               'link': MAIN_URL + link['href']})
    subtitles_list.sort(key=lambda s: -int(s['rating']))
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    page = session.get(sub['link'], timeout=SEARCH_TIMEOUT)
    page.raise_for_status()
    button = BeautifulSoup(page.text, 'html.parser').select_one('a.download-subtitle[href]')
    if not button:
        raise Exception('yifysubtitles: no download link on %s' % sub['link'])
    link = requests.compat.urljoin(MAIN_URL, button['href'])
    log(__name__, "downloading %s" % link)
    r = session.get(link, headers={'Referer': sub['link']}, timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    if not r.content or r.content.lstrip()[:1] == b'<':
        raise Exception('yifysubtitles: download returned no subtitle file')
    filepath = os.path.join(tmp_sub_dir, os.path.basename(link))
    with open(filepath, 'wb') as f:
        f.write(r.content)
    return False, sub['language_name'], filepath
