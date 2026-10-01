# -*- coding: utf-8 -*-
"""moviesubtitles.org: movies only, 13 languages, downloads are zip files."""
import os
import re

import requests
from bs4 import BeautifulSoup

from ..user_agents import get_random_ua
from ..utilities import languageTranslate, log

MAIN_URL = "https://www.moviesubtitles.org"
# ISO 639-1 code -> flag name used by the site (ar br de en es fr gr hu it pl ru tr ua)
SITE_FLAGS = {'el': 'gr', 'pb': 'br', 'uk': 'ua'}

session = requests.Session()
session.headers.update({'User-Agent': get_random_ua(), 'Referer': MAIN_URL + '/'})


def wanted_languages(*names):
    """{ISO 639-1 code: requested language name} for the requested languages known to the plugin."""
    wanted = {}
    for name in reversed(names):
        code = languageTranslate(name, 0, 2) if name else None
        if code:
            wanted['pb' if code == 'pt-br' else code] = name
    return wanted


def normalize(text):
    """'Matrix, The' -> 'the matrix'"""
    text = re.sub(r'^(.*), (the|a|an)$', r'\2 \1', text.strip(), flags=re.I)
    return ' '.join(re.findall(r'[^\W_]+', re.sub(r"['`]", '', text.lower()).replace('&', 'and')))


def find_movie(title, year):
    # the site answers search.php with HTTP 500 but a valid result page
    r = session.post(MAIN_URL + "/search.php", data={'q': title}, timeout=15)
    movies = re.findall(r'<a\s+href="(/movie-\d+\.html)">([^<]+?)\s*\((\d{4})\)</a>', r.text)
    log(__name__, "search '%s': %s" % (title, movies))
    same_title = [m for m in movies if normalize(m[1]) == normalize(title)]
    if year:  # allow +-1 year, or a single movie with that title
        same_title = [m for m in same_title if abs(int(m[2]) - int(year)) <= 1] or same_title[:len(same_title) == 1]
    return MAIN_URL + same_title[0][0] if same_title else None


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = wanted_languages(lang1, lang2, lang3)
    flags = dict((SITE_FLAGS.get(code, code), code) for code in wanted)
    if tvshow or not title:  # the site has no tv shows
        return [], "", ""
    url = find_movie(title, year)
    if not url:
        return [], "", ""
    r = session.get(url, timeout=15)
    r.raise_for_status()
    subtitles_list = []
    for div in BeautifulSoup(r.text, 'html.parser').select('div.subtitle'):
        img = div.find('img', src=re.compile(r'flags/'))
        link = div.find('a', href=re.compile(r'^/subtitle-\d+\.html'))
        if not img or not link or not link.b or img.get('alt') not in flags:
            continue
        name = re.sub(r'\s+\S+ subtitles\b|\s*\(\)', '', link.b.get_text(' ', strip=True))  # drop "english subtitles"
        parts = div.find('td', title='parts')
        if parts and parts.get_text(strip=True) not in ('', '1'):
            name += " [%s CDs]" % parts.get_text(strip=True)
        subtitles_list.append({'filename': name, 'id': link['href'], 'sync': False,
                               'language_name': wanted[flags[img['alt']]]})
    log(__name__, "%d subtitles on %s" % (len(subtitles_list), url))
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    r = session.get(MAIN_URL + sub['id'].replace('/subtitle-', '/download-'), timeout=30)
    r.raise_for_status()
    if not r.content or r.content.lstrip()[:1] == b'<':
        raise Exception(f"no subtitle file for {sub['id']}")
    ext = '.zip' if r.content[:2] == b'PK' else '.rar' if r.content[:4] == b'Rar!' else '.srt'
    path = os.path.join(tmp_sub_dir, "moviesubtitles_%s%s" % (re.sub(r'\D', '', sub['id']), ext))
    with open(path, 'wb') as f:
        f.write(r.content)
    return False, sub['language_name'], path
