# -*- coding: utf-8 -*-
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..utilities import createSession, langCode, log, matchTitle, saveSubtitle, wantedLanguages

MAIN_URL = "https://yifysubtitles.ch"
SEARCH_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

session = createSession(MAIN_URL + '/')


def find_movie(title, year):
    """Returns the IMDb id of the best matching search result or None."""
    r = session.get(MAIN_URL + '/ajax/search/', params={'mov': title}, timeout=SEARCH_TIMEOUT,
                    headers={'X-Requested-With': 'XMLHttpRequest'})
    r.raise_for_status()
    results = []
    for item in r.json() or []:
        movie = item.get('movie', '').strip()
        m = re.match(r'(.*?)\s+(\d{4})$', movie)  # "The Matrix 1999"
        results.append((m.group(1), m.group(2), item.get('imdb')) if m else (movie, None, item.get('imdb')))
    return matchTitle(title, year, results)


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    if tvshow:  # movies only
        return [], "", ""
    wanted = wantedLanguages(lang1, lang2, lang3)
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
        code = lang and langCode(lang.get_text(strip=True))
        if not link or code not in wanted:
            continue
        names = [n for n in link.stripped_strings if n.lower() != 'subtitle']
        rating = row.select_one('td.rating-cell')
        rating = rating.get_text(strip=True) if rating else '0'
        subtitles_list.append({'filename': names[0] if names else title, 'language_name': wanted[code],
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
    link = urljoin(MAIN_URL, button['href'])
    log(__name__, "downloading %s" % link)
    r = session.get(link, headers={'Referer': sub['link']}, timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    return False, sub['language_name'], saveSubtitle(tmp_sub_dir, link, r.content)
