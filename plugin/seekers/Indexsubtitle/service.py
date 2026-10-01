# -*- coding: utf-8 -*-
import json
import re
import time

from ..utilities import createSession, episodeFilters, langCode, log, matchTitle, saveSubtitle, wantedLanguages

MAIN_URL = "https://indexsubtitle.cc"
SEARCH_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

session = createSession(MAIN_URL + '/')


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


def find_title(title, year=None):
    """Returns the /subtitles/<slug> path of the best matching search result or None."""
    r = request('POST', MAIN_URL + '/search', data={'query': title}, timeout=SEARCH_TIMEOUT,
                headers={'X-Requested-With': 'XMLHttpRequest'})
    results = []
    for item in json.loads(r.text) if r.text.strip() else []:  # empty body = nothing found
        m = re.match(r'(.*?)\s*\((\d{4})\)\s*$', item.get('title', ''))
        results.append((m.group(1), m.group(2), item['url']) if m else (item.get('title', ''), None, item['url']))
    return matchTitle(title, year, results)


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = wantedLanguages(lang1, lang2, lang3)
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
    if tvshow:
        this_episode, any_episode, this_season = episodeFilters(int(season), int(episode))
    subtitles_list = []
    for item in json.loads(m.group(1)):
        code = langCode(item.get('language'))
        if code not in wanted:
            continue
        name = item.get('title', '').strip()
        # this episode or a pack of this season
        if tvshow and not (this_episode.search(name) or not any_episode.search(name) and this_season.search(name)):
            continue
        subtitles_list.append({'filename': name, 'language_name': wanted[code], 'sync': False,
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
    return False, sub['language_name'], saveSubtitle(tmp_sub_dir, 'indexsubtitle_%s' % sub_id, r.content)
