# -*- coding: utf-8 -*-
import os
import re

import requests
from bs4 import BeautifulSoup

from ..user_agents import get_random_ua
from ..utilities import languageTranslate, log

MAIN_URL = "https://my-subs.co"
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


def get_soup(url, params=None):
    r = session.get(url, params=params, timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'html.parser')


def find_title(title, year, tvshow):
    """Returns the movie (film-versions-...) or show (showlistsubtitles-...) path of the best search result."""
    kind = 'showlistsubtitles-' if tvshow else 'film-versions-'
    wanted = normalize_title(title)
    exact, partial = [], []
    for a in get_soup(MAIN_URL + '/search.php', {'key': title}).select('a.list-group-item'):
        href = a.get('href', '')
        if not href.startswith('/' + kind):
            continue
        m = re.match(r'(.*?)\s*\((\d{4})\)\s*$', a.get_text(' ', strip=True))
        found, found_year = (m.group(1), m.group(2)) if m else (a.get_text(' ', strip=True), None)
        if normalize_title(found) == wanted:
            exact.append((found_year, href))
        elif wanted in normalize_title(found):
            partial.append((found_year, href))
    if year:
        for found_year, href in exact + partial:
            if found_year == str(year):
                return href
    return exact[0][1] if exact else None


def movie_subtitles(soup):
    """Movie page: per language a <h3> followed by a list of releases."""
    for a in soup.select('div.panel-body a.list-group-item[href^="/downloads/"]'):
        flag = a.find('span', title=True)
        name = a.find('strong')
        if flag and name:
            yield flag['title'], name.get_text(strip=True), a['href']


def episode_subtitles(soup, prefix):
    """Episode page: one block per version with language flag and download button."""
    for a in soup.select('a[href^="/downloads/"]'):
        version = a.find_previous('div', class_='version')
        flag = a.find_previous('span', class_='flag-icon', title=True)
        if version and flag:
            name = version.get_text(' ', strip=True).replace('Version:', '').strip()
            yield flag['title'], '%s %s' % (prefix, name), a['href']


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = set(filter(None, (lang_code(lang) for lang in (lang1, lang2, lang3))))
    path = find_title(tvshow or title, None if tvshow else year, bool(tvshow))
    log(__name__, "search '%s' (%s) -> %s" % (tvshow or title, year, path))
    if not path:
        return [], "", ""
    if tvshow:
        # /showlistsubtitles-<id>-<slug>  ->  /versions-<id>-<episode>-<season>-<slug>-subtitles
        show_id, slug = re.match(r'/showlistsubtitles-(\d+)-(.+)', path).groups()
        url = '%s/versions-%s-%d-%d-%s-subtitles' % (MAIN_URL, show_id, int(episode), int(season), slug)
        entries = episode_subtitles(get_soup(url), '%s S%02dE%02d' % (tvshow, int(season), int(episode)))
    else:
        entries = movie_subtitles(get_soup(MAIN_URL + path))
    subtitles_list = []
    for site_lang, name, link in entries:
        code = lang_code(site_lang)
        if code in wanted:
            subtitles_list.append({'filename': name, 'language_name': languageTranslate(code, 2, 0), 'sync': False,
                                   'link': MAIN_URL + link})
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    # the download page shows a 10 s countdown in javascript, the real link is in the script
    page = session.get(sub['link'], timeout=SEARCH_TIMEOUT)
    page.raise_for_status()
    m = re.search(r'REAL_URL\s*=\s*"([^"]+)"', page.text)
    if not m:
        raise Exception('my-subs.co: no download link on %s' % sub['link'])
    link = MAIN_URL + m.group(1).replace('\\/', '/')
    log(__name__, "downloading %s" % link)
    r = session.get(link, headers={'Referer': sub['link']}, timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    if not r.content or r.content.lstrip()[:1] == b'<':
        raise Exception('my-subs.co: download returned no subtitle file')
    filename = os.path.basename(link) or 'mysubs.srt'
    m = re.search(r'filename="?([^";]+)', r.headers.get('content-disposition', ''))
    if m:
        filename = os.path.basename(m.group(1))
    filepath = os.path.join(tmp_sub_dir, filename)
    with open(filepath, 'wb') as f:
        f.write(r.content)
    return False, sub['language_name'], filepath
