# -*- coding: utf-8 -*-
"""subf2m.co (Subscene mirror). The site search (/subtitles/searchbytitle) answers with
HTTP 500, so title pages are opened by their Subscene slug: /subtitles/the-matrix,
/subtitles/breaking-bad-first-season."""
import re

from bs4 import BeautifulSoup

from ..utilities import SEASONS, createSession, episodeFilters, langCode, log, normalizeTitle, romanVariations, \
    saveSubtitle, wantedLanguages, yearMatch

MAIN_URL = "https://subf2m.co"
SEARCH_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

session = createSession(MAIN_URL + '/')


def slug_candidates(name, year, season):
    """'Rocky II' -> rocky-ii, rocky-2 (+ -<year> or -<ordinal>-season)"""
    slugs = ['-'.join(words) for words in romanVariations(normalizeTitle(name).split())]
    if season:
        ordinal = SEASONS[season].lower() if season < len(SEASONS) else str(season)
        return ['%s-%s-season' % (s, ordinal) for s in slugs] + slugs  # season page, else complete series
    return slugs + ['%s-%s' % (s, year) for s in slugs if year]


def get_title_page(name, year, season):
    for slug in slug_candidates(name, year, season):
        r = session.get("%s/subtitles/%s" % (MAIN_URL, slug), timeout=SEARCH_TIMEOUT)
        if r.status_code == 404:
            continue
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        if not soup.select('li.item a.download'):
            continue
        m = re.search(r'Year:\s*</strong>\s*(\d{4})', r.text)
        if m and not yearMatch(m.group(1), year):
            log(__name__, "%s is from %s, not %s" % (slug, m.group(1), year))
            continue
        log(__name__, "title page: %s" % r.url)
        return soup
    return None


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = wantedLanguages(lang1, lang2, lang3)
    season = int(season) if tvshow and season else 0
    # season pages carry the year of the season, not of the show
    soup = get_title_page(tvshow or title, None if tvshow else year, season)
    if soup is None:
        return [], "", ""
    if season:
        this_episode, any_episode, this_season = episodeFilters(season, int(episode))
    episodes, packs = [], []
    for item in soup.select('li.item'):
        lang = item.select_one('span.language')
        link = item.select_one('a.download[href]')
        releases = [li.get_text(strip=True) for li in item.select('ul.scrolllist li')]
        if not lang or not link or not releases and season:
            continue
        releases = releases or ["%s (%s)" % (title, link['href'].rsplit('/', 1)[-1])]  # uploaded without release name
        code = langCode(lang.get_text(strip=True))
        if code not in wanted:
            continue
        sub = {'filename': releases[0], 'link': MAIN_URL + link['href'], 'language_name': wanted[code], 'sync': False}
        if not season:
            episodes.append(sub)
            continue
        matching = [rel for rel in releases if this_episode.search(rel)]
        if matching:
            sub['filename'] = matching[0]
            episodes.append(sub)
        elif not any(any_episode.search(rel) for rel in releases) and any(this_season.search(rel) for rel in releases):
            packs.append(sub)  # whole season in one archive
    log(__name__, "%d subtitles, %d season packs" % (len(episodes), len(packs)))
    return episodes + packs, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    r = session.get(sub['link'] + '/download', headers={'Referer': sub['link']}, timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    path = saveSubtitle(tmp_sub_dir, "subf2m_%s" % sub['link'].rsplit('/', 1)[-1], r.content)
    return False, sub['language_name'], path
