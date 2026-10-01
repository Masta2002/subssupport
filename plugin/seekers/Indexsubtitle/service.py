# -*- coding: utf-8 -*-
import json
import os
import re
import time

import requests

from ..user_agents import get_random_ua
from ..utilities import languageTranslate, log

MAIN_URL = "https://indexsubtitle.cc"
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


def request(method, url, **kwargs):
    """session.request() that waits once when the site rate-limits (about 5 requests per 10 s)."""
    r = session.request(method, url, **kwargs)
    retry = r.headers.get('Retry-After', '')
    if r.status_code == 429 and retry.isdigit() and int(retry) <= 10:
        log(__name__, "rate limited, retrying in %s s" % retry)
        time.sleep(int(retry) + 1)
        r = session.request(method, url, **kwargs)
    r.raise_for_status()
    return r


def normalize_title(title):
    return re.sub(r'[^a-z0-9]+', ' ', (title or '').lower()).strip()


def find_title(title, year=None):
    """Returns the /subtitles/<slug> path of the best matching search result or None."""
    r = request('POST', MAIN_URL + '/search', data={'query': title}, timeout=SEARCH_TIMEOUT,
                headers={'X-Requested-With': 'XMLHttpRequest'})
    results = json.loads(r.text) if r.text.strip() else []  # empty body = nothing found
    wanted = normalize_title(title)
    exact, partial = [], []
    for item in results:
        m = re.match(r'(.*?)\s*\((\d{4})\)\s*$', item.get('title', ''))
        found, found_year = (m.group(1), m.group(2)) if m else (item.get('title', ''), None)
        if normalize_title(found) == wanted:
            exact.append((found_year, item['url']))
        elif wanted in normalize_title(found):
            partial.append((found_year, item['url']))
    if year:
        for found_year, url in exact + partial:
            if found_year == str(year):
                return url
    return exact[0][1] if exact else None


def episode_match(name, season, episode):
    m = re.search(r'S(\d{1,2})[ ._-]*E(\d{1,3})|\b(\d{1,2})x(\d{2,3})\b', name, re.I)
    if m:
        s, e = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        return int(s) == season and int(e) == episode
    m = re.search(r'\bS(?:eason)?[ ._-]*(\d{1,2})\b', name, re.I)  # season pack
    return bool(m) and int(m.group(1)) == season


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = set(filter(None, (lang_code(lang) for lang in (lang1, lang2, lang3))))
    name, year = tvshow or title, None if tvshow else year
    # pages are /subtitles/<slug>[-<year>]; guess it first, the search api is rate limited harder
    slug = '/subtitles/' + re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') + ('-%s' % year if year else '')
    m = ttl = None
    for path in (slug, None):
        path = path or find_title(name, year)
        log(__name__, "search '%s' (%s) -> %s" % (name, year, path))
        if not path:
            return [], "", ""
        page = MAIN_URL + path
        content = request('GET', page, timeout=SEARCH_TIMEOUT).text  # unknown slug redirects to home
        m = re.search(r'data:\s*(\[\{"title".*?\}\])\s*,\s*columns', content, re.S)
        ttl = re.search(r'ttl\s*=\s*(\d+)', content)
        if m and ttl:
            break
    else:
        return [], "", ""
    subtitles_list = []
    for item in json.loads(m.group(1)):
        code = lang_code(item.get('language'))
        if code not in wanted:
            continue
        name = item.get('title', '').strip()
        if tvshow and not episode_match(name, int(season), int(episode)):
            continue
        subtitles_list.append({'filename': name, 'language_name': languageTranslate(code, 2, 0), 'sync': False,
                               'url': item['url'], 'site_lang': item['language'], 'ttl': ttl.group(1),
                               'page': page})
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    url = sub['url']  # <slug>/<language>/<id>
    sub_id = url.split('/')[2]
    info = request('POST', MAIN_URL + '/subtitlesInfo', data={'id': sub_id, 'lang': sub['site_lang'], 'url': url},
                   headers={'X-Requested-With': 'XMLHttpRequest', 'Referer': sub['page']}, timeout=SEARCH_TIMEOUT)
    token = info.json().get('token')
    if not token:
        raise Exception('indexsubtitle.cc: no download token for %s' % url)
    # same as the site's javascript: url.replace(/[^\w ]/, '').replace(/\//g, '_')
    zp = re.sub(r'[^\w ]', '', url, count=1).replace('/', '_')
    link = '%s/d/%s/%s/%s/%s.zip' % (MAIN_URL, sub_id, sub['ttl'], token, zp)
    log(__name__, "downloading %s" % link)
    r = request('GET', link, headers={'Referer': sub['page']}, timeout=DOWNLOAD_TIMEOUT)
    if not r.content or r.content.lstrip()[:1] == b'<':
        raise Exception('indexsubtitle.cc: download returned no subtitle file')
    filepath = os.path.join(tmp_sub_dir, 'indexsubtitle_%s.zip' % sub_id)
    with open(filepath, 'wb') as f:
        f.write(r.content)
    return False, sub['language_name'], filepath
