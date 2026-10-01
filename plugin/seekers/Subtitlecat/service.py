# -*- coding: utf-8 -*-
"""subtitlecat.com: every subtitle has an original language plus machine translations
that were already generated on the site (new translations need JavaScript, so only
existing ones are offered)."""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup

from ..user_agents import get_random_ua
from ..utilities import languageTranslate, log

MAIN_URL = "https://www.subtitlecat.com/"
# ISO 639-1 codes that differ on the site
SITE_CODES = {'he': 'iw', 'zh': 'zh-CN', 'pb': 'pt-BR'}
MT_PAGES = 8  # detail pages checked for ready machine translations

session = requests.Session()
session.headers.update({'User-Agent': get_random_ua(), 'Referer': MAIN_URL})


def wanted_languages(*names):
    """{ISO 639-1 code: requested language name} for the requested languages known to the plugin."""
    wanted = {}
    for name in reversed(names):
        code = languageTranslate(name, 0, 2) if name else None
        if code:
            wanted['pb' if code == 'pt-br' else code] = name
    return wanted


def search(query):
    r = session.get(MAIN_URL + "index.php", params={'search': query}, timeout=15)
    r.raise_for_status()
    rows = []
    for td in BeautifulSoup(r.text, 'html.parser').select('tr > td:first-child'):
        a = td.find('a', href=True)
        if not a or not a['href'].startswith('subs/'):
            continue
        m = re.search(r'\(translated from ([^)]+)\)', td.get_text(' ', strip=True))
        orig = m.group(1).strip() if m else '?'
        rows.append((a.get_text(strip=True), urljoin(MAIN_URL, a['href']), orig, languageTranslate(orig, 0, 2)))
    log(__name__, "%d results for '%s'" % (len(rows), query))
    return rows


def get_page_links(url):
    """{site language code: download url} of a subtitle page, '' = original file."""
    r = session.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    links = dict((a['id'][9:], urljoin(MAIN_URL, a['href']))
                 for a in soup.select('a[id^="download_"][href]') if a['href'].endswith('.srt'))
    m = re.search(r"translate_from_server_folder\('[\w-]+', '([^']+)', '([^']+)'\)", r.text)
    if m:
        links[''] = urljoin(MAIN_URL, m.group(2) + m.group(1))
    return links


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = wanted_languages(lang1, lang2, lang3)
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
    for (name, url, orig, orig_code), links in zip(candidates, pages):
        for code, lang in wanted.items():
            if code != orig_code and SITE_CODES.get(code, code) in links:
                subtitles_list.append({'filename': "%s [machine translated from %s]" % (name, orig), 'url': url,
                                       'language_name': lang, 'code': code, 'translated': True, 'sync': False})
    return subtitles_list, "", ""


def _safe(func, *args):
    try:
        return func(*args)
    except requests.RequestException as e:
        log(__name__, "request failed: %s" % e)
        return {}


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    links = get_page_links(sub['url'])
    url = links.get(SITE_CODES.get(sub['code'], sub['code']))
    if not url and not sub.get('translated'):
        url = links.get('')  # original file
    if not url:
        raise Exception(f"no {sub['language_name']} subtitle on {sub['url']}")
    r = session.get(url, timeout=30)
    r.raise_for_status()
    if b'-->' not in r.content:  # some files are (translated) error pages
        raise Exception(f"no subtitle in {url}")
    path = os.path.join(tmp_sub_dir, os.path.basename(unquote(url)))
    with open(path, 'wb') as f:
        f.write(r.content)
    return False, sub['language_name'], path
