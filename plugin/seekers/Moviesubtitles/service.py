# -*- coding: utf-8 -*-
"""moviesubtitles.org: movies only, 13 languages, downloads are zip files."""
import html
import re

from bs4 import BeautifulSoup

from ..utilities import createSession, log, matchTitle, saveSubtitle, wantedLanguages

MAIN_URL = "https://www.moviesubtitles.org"
SEARCH_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30
# ISO 639-1 code -> flag name used by the site (ar br de en es fr gr hu it pl ru tr ua)
SITE_FLAGS = {'el': 'gr', 'pt-br': 'br', 'uk': 'ua'}

session = createSession(MAIN_URL + '/')


def get_page(url, **kwargs):
    # the site answers search.php with HTTP 500 but a valid result page and sends no charset
    r = session.request('POST' if 'data' in kwargs else 'GET', url, timeout=SEARCH_TIMEOUT, **kwargs)
    r.encoding = 'utf-8'
    return r


def find_movie(title, year):
    r = get_page(MAIN_URL + "/search.php", data={'q': title})
    movies = re.findall(r'<a\s+href="(/movie-\d+\.html)">([^<]+?)\s*\((\d{4})\)</a>', r.text)
    log(__name__, "search '%s': %s" % (title, movies))
    results = []
    for url, name, found_year in movies:
        # "Fate of the Furious, The (Fast and Furious 8)": main or alternative title
        for alt in re.match(r'(.*?)(?:\s*\(([^)]*)\))?$', html.unescape(name)).groups():
            if alt:
                results.append((alt, found_year, url))
    url = matchTitle(title, year, results)
    return MAIN_URL + url if url else None


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = wantedLanguages(lang1, lang2, lang3)
    flags = dict((SITE_FLAGS.get(code, code), code) for code in wanted)
    if tvshow or not title:  # the site has no tv shows
        return [], "", ""
    url = find_movie(title, year)
    if not url:
        return [], "", ""
    r = get_page(url)
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
    r = session.get(MAIN_URL + sub['id'].replace('/subtitle-', '/download-'), timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    path = saveSubtitle(tmp_sub_dir, "moviesubtitles_%s" % re.sub(r'\D', '', sub['id']), r.content)
    return False, sub['language_name'], path
