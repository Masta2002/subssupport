# -*- coding: utf-8 -*-
"""subtitlecat.com: every subtitle has an original language plus machine translations
that were already generated on the site (new translations need JavaScript, so only
existing ones are offered)."""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup

from ..utilities import createSession, langCode, log, saveSubtitle, wantedLanguages

MAIN_URL = "https://www.subtitlecat.com/"
SEARCH_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30
# ISO 639-1 codes that differ on the site
SITE_CODES = {'he': 'iw', 'zh': 'zh-CN', 'pt-br': 'pt-BR'}
MT_PAGES = 8  # detail pages checked for ready machine translations

session = createSession(MAIN_URL)


def search(query):
    r = session.get(MAIN_URL + "index.php", params={'search': query}, timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    rows = []
    for td in BeautifulSoup(r.text, 'html.parser').select('tr > td:first-child'):
        a = td.find('a', href=True)
        if not a or not a['href'].startswith('subs/'):
            continue
        m = re.search(r'\(translated from ([^)]+)\)', td.get_text(' ', strip=True))
        orig = m.group(1).strip() if m else '?'
        rows.append((a.get_text(strip=True), urljoin(MAIN_URL, a['href']), orig, langCode(orig)))
    log(__name__, "%d results for '%s'" % (len(rows), query))
    return rows


def get_page_links(url):
    """{site language code: download url} of a subtitle page, '' = original file."""
    r = session.get(url, timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    links = dict((a['id'][9:], urljoin(MAIN_URL, a['href']))
                 for a in soup.select('a[id^="download_"][href]') if a['href'].endswith('.srt'))
    m = re.search(r"translate_from_server_folder\('[\w-]+', '([^']+)', '([^']+)'\)", r.text)
    if m:
        links[''] = urljoin(MAIN_URL, m.group(2) + m.group(1))
    return links


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = wantedLanguages(lang1, lang2, lang3)
    if tvshow:
        rows = search("%s S%02dE%02d" % (tvshow, int(season), int(episode)))
    else:
        rows = year and search("%s %s" % (title, year)) or search(title)
    subtitles_list = [{'filename': name, 'url': url, 'language_name': wanted[code], 'code': code, 'sync': False}
                      for name, url, orig, code in rows if code in wanted]
    # other languages: offer machine translations the site has already made for the best hits
    candidates = [row for row in rows if set(wanted) - {row[3]}][:MT_PAGES]
    with ThreadPoolExecutor(4) as pool:
        pages = list(pool.map(lambda row: _safe(get_page_links, row[1]), candidates))
    for (name, url, orig, orig_code), links in zip(candidates, pages, strict=True):
        for code, lang in wanted.items():
            link = links.get(SITE_CODES.get(code, code))
            if code != orig_code and link:
                subtitles_list.append({'filename': "%s [machine translated from %s]" % (name, orig), 'url': url,
                                       'link': link, 'language_name': lang, 'code': code, 'sync': False})
    return subtitles_list, "", ""


def _safe(func, *args):
    try:
        return func(*args)
    except requests.RequestException as e:
        log(__name__, "request failed: %s" % e)
        return {}


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    url = sub.get('link')  # machine translations were resolved by the search
    if not url:
        links = get_page_links(sub['url'])
        url = links.get(SITE_CODES.get(sub['code'], sub['code'])) or links.get('')  # else the original file
    if not url:
        raise Exception("no %s subtitle on %s" % (sub['language_name'], sub['url']))
    r = session.get(url, timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    if b'-->' not in r.content:  # some files are (translated) error pages
        raise Exception("no subtitle in %s" % url)
    return False, sub['language_name'], saveSubtitle(tmp_sub_dir, unquote(url), r.content)
