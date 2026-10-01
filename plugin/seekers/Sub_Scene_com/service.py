# -*- coding: utf-8 -*-
"""sub-scene.com (Subscene archive). /search is behind a Cloudflare challenge, so titles are
looked up with the /suggest JSON API that the site's search box uses."""
import os
import re

import requests
from bs4 import BeautifulSoup

from ..user_agents import get_random_ua
from ..utilities import languageTranslate, log

MAIN_URL = "https://sub-scene.com"
SEASONS = ["Specials", "First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth",
           "Eleventh", "Twelfth", "Thirteenth", "Fourteenth", "Fifteenth", "Sixteenth", "Seventeenth", "Eighteenth",
           "Nineteenth", "Twentieth", "Twenty-first", "Twenty-second", "Twenty-third", "Twenty-fourth", "Twenty-fifth"]
# Subscene language names that the plugin does not know
LANG_ALIASES = {'Farsi/Persian': 'fa', 'Brazillian Portuguese': 'pb', 'Chinese BG code': 'zh', 'Big 5 code': 'zh',
                'Ukranian': 'uk'}

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
    return ' '.join(re.findall(r'[^\W_]+', text.lower().replace('&', 'and')))


def find_title_id(name, year, season):
    r = session.get(MAIN_URL + "/suggest", params={'query': name}, timeout=15)
    r.raise_for_status()
    data = r.json()
    if season:
        items = data.get('tv') or data.get('film') or []
        wanted = ["%s %s season" % (normalize(name), SEASONS[season].lower()) if season < len(SEASONS) else None,
                  "%s season %d" % (normalize(name), season), normalize(name)]
        for title in wanted:
            for item in items:
                if title and normalize(item.get('name', '')) == title:
                    return item['id'], item['name']
        return None, None
    items = (data.get('film') or []) + (data.get('tv') or [])
    same_name = [i for i in items if normalize(i.get('name', '')) == normalize(name)]
    for candidates in ([i for i in same_name if str(i.get('year')) == str(year)], same_name,
                       [i for i in items if year and str(i.get('year')) == str(year)]):
        if candidates:
            return candidates[0]['id'], candidates[0]['name']
    return None, None


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = wanted_languages(lang1, lang2, lang3)
    season = int(season) if tvshow and season else 0
    title_id, found = find_title_id(tvshow or title, year, season)
    log(__name__, "suggest match for '%s' (%s): %s %s" % (tvshow or title, year or season, title_id, found))
    if not title_id:
        return [], "", ""
    r = session.get("%s/subscene/%s" % (MAIN_URL, title_id), timeout=15)
    r.raise_for_status()
    if season:
        ep = int(episode)
        episode_re = re.compile(r'(?:s0*%d[ ._-]*e0*%d|\b%d?x0*%d)(?!\d)' % (season, ep, season, ep), re.I)
        any_episode_re = re.compile(r's\d+[ ._-]*e\d+|\b\d+x\d+\b|\be(?:p|pisode)?[ ._-]*\d+\b', re.I)
        season_re = re.compile(r's0*%d(?!\d)|season[ ._-]*0*%d(?!\d)|%s season' % (season, season, SEASONS[season]), re.I)
    episodes, packs, seen = [], [], set()
    for a in BeautifulSoup(r.text, 'html.parser').select('td.a1 a[href^="/subtitle/"]'):
        sub_id = a['href'].rsplit('/', 1)[-1]
        lang = a.select_one('span.l')
        release = a.select_one('span.new')
        if not lang or not release or sub_id in seen:
            continue
        lang, release = lang.get_text(strip=True), release.get_text(' ', strip=True) or "%s (%s)" % (found, sub_id)
        code = LANG_ALIASES.get(lang) or languageTranslate(lang, 0, 2)
        if code not in wanted:
            continue
        seen.add(sub_id)
        sub = {'filename': release, 'id': sub_id, 'language_name': wanted[code], 'sync': False}
        if not season or episode_re.search(release):
            episodes.append(sub)
        elif not any_episode_re.search(release) and season_re.search(release):
            packs.append(sub)  # whole season in one archive
    log(__name__, "%d subtitles, %d season packs" % (len(episodes), len(packs)))
    return episodes + packs, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    r = session.get("%s/download/%s" % (MAIN_URL, sub['id']), timeout=30)
    r.raise_for_status()
    if not r.content or r.content.lstrip()[:1] == b'<':
        raise Exception(f"no subtitle file for id {sub['id']}")
    ext = '.zip' if r.content[:2] == b'PK' else '.rar' if r.content[:4] == b'Rar!' else '.srt'
    path = os.path.join(tmp_sub_dir, "sub-scene_%s%s" % (sub['id'], ext))
    with open(path, 'wb') as f:
        f.write(r.content)
    return False, sub['language_name'], path
