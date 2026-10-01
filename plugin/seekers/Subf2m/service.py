# -*- coding: utf-8 -*-
"""subf2m.co (Subscene mirror). The site search (/subtitles/searchbytitle) answers with
HTTP 500, so title pages are opened by their Subscene slug: /subtitles/the-matrix,
/subtitles/breaking-bad-first-season."""
import os
import re

import requests
from bs4 import BeautifulSoup

from ..user_agents import get_random_ua
from ..utilities import languageTranslate, log

MAIN_URL = "https://subf2m.co"
SEASONS = ["Specials", "First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth",
           "Eleventh", "Twelfth", "Thirteenth", "Fourteenth", "Fifteenth", "Sixteenth", "Seventeenth", "Eighteenth",
           "Nineteenth", "Twentieth", "Twenty-first", "Twenty-second", "Twenty-third", "Twenty-fourth", "Twenty-fifth"]
# Subscene language names that the plugin does not know
LANG_ALIASES = {'Farsi/Persian': 'fa', 'Brazillian Portuguese': 'pb', 'Chinese BG code': 'zh', 'Big 5 code': 'zh',
                'Ukranian': 'uk'}
ROMAN = {'2': 'ii', '3': 'iii', '4': 'iv', '5': 'v', '6': 'vi', '7': 'vii', '8': 'viii', '9': 'ix', '10': 'x'}

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


def slugify(text):
    """'Dune: Part Two' -> 'dune-part-two'"""
    return '-'.join(re.findall(r'[^\W_]+', re.sub(r"['`]", '', text.lower()).replace('&', 'and')))


def slug_candidates(name, year, season):
    slugs = [slugify(name)]
    roman = '-'.join(ROMAN.get(w, w) for w in slugs[0].split('-'))  # Rocky 2 -> rocky-ii
    if roman != slugs[0]:
        slugs.append(roman)
    if season:
        ordinal = SEASONS[season].lower() if season < len(SEASONS) else str(season)
        return ['%s-%s-season' % (s, ordinal) for s in slugs] + slugs  # season page, else complete series
    return slugs + ['%s-%s' % (s, year) for s in slugs if year]


def get_title_page(name, year, season):
    for slug in slug_candidates(name, year, season):
        r = session.get("%s/subtitles/%s" % (MAIN_URL, slug), timeout=15)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        if not soup.select('li.item a.download'):
            continue
        m = re.search(r'Year:\s*</strong>\s*(\d{4})', r.text)
        if year and m and abs(int(m.group(1)) - int(year)) > 1:
            log(__name__, "%s is from %s, not %s" % (slug, m.group(1), year))
            continue
        log(__name__, "title page: %s" % r.url)
        return soup
    return None


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = wanted_languages(lang1, lang2, lang3)
    season = int(season) if tvshow and season else 0
    soup = get_title_page(tvshow or title, year, season)
    if soup is None:
        return [], "", ""
    if season:
        ep = int(episode)
        episode_re = re.compile(r'(?:s0*%d[ ._-]*e0*%d|\b%d?x0*%d)(?!\d)' % (season, ep, season, ep), re.I)
        any_episode_re = re.compile(r's\d+[ ._-]*e\d+|\b\d+x\d+\b|\be(?:p|pisode)?[ ._-]*\d+\b', re.I)
        season_re = re.compile(r's0*%d(?!\d)|season[ ._-]*0*%d(?!\d)|%s season' % (season, season, SEASONS[season]), re.I)
    episodes, packs = [], []
    for item in soup.select('li.item'):
        lang = item.select_one('span.language')
        link = item.select_one('a.download[href]')
        releases = [li.get_text(strip=True) for li in item.select('ul.scrolllist li')]
        if not lang or not link or not releases and season:
            continue
        releases = releases or ["%s (%s)" % (title, link['href'].rsplit('/', 1)[-1])]  # uploaded without release name
        code = LANG_ALIASES.get(lang.get_text(strip=True)) or languageTranslate(lang.get_text(strip=True), 0, 2)
        if code not in wanted:
            continue
        sub = {'filename': releases[0], 'link': MAIN_URL + link['href'], 'language_name': wanted[code], 'sync': False}
        if not season:
            episodes.append(sub)
            continue
        matching = [rel for rel in releases if episode_re.search(rel)]
        if matching:
            sub['filename'] = matching[0]
            episodes.append(sub)
        elif not any(any_episode_re.search(rel) for rel in releases) and any(season_re.search(rel) for rel in releases):
            packs.append(sub)  # whole season in one archive
    log(__name__, "%d subtitles, %d season packs" % (len(episodes), len(packs)))
    return episodes + packs, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    r = session.get(sub['link'] + '/download', headers={'Referer': sub['link']}, timeout=30)
    r.raise_for_status()
    if not r.content or r.content.lstrip()[:1] == b'<':
        raise Exception(f"no subtitle file at {sub['link']}")
    ext = '.zip' if r.content[:2] == b'PK' else '.rar' if r.content[:4] == b'Rar!' else '.srt'
    path = os.path.join(tmp_sub_dir, "subf2m_%s%s" % (sub['link'].rsplit('/', 1)[-1], ext))
    with open(path, 'wb') as f:
        f.write(r.content)
    return False, sub['language_name'], path
