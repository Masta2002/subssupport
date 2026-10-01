# -*- coding: utf-8 -*-
"""sub-scene.com (Subscene archive). /search is behind a Cloudflare challenge, so titles are
looked up with the /suggest JSON API that the site's search box uses."""
from bs4 import BeautifulSoup

from ..utilities import SEASONS, createSession, episodeFilters, langCode, log, matchTitle, normalizeTitle, \
    saveSubtitle, wantedLanguages

MAIN_URL = "https://sub-scene.com"
SEARCH_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

session = createSession(MAIN_URL + '/')


def find_title_id(name, year, season):
    """(id, name) of the matching title or season page, (None, None) if not found."""
    r = session.get(MAIN_URL + "/suggest", params={'query': name}, timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if season:
        items = data.get('tv') or data.get('film') or []
        wanted = ["%s season %d" % (normalizeTitle(name), season), normalizeTitle(name)]
        if season < len(SEASONS):
            wanted.insert(0, "%s %s season" % (normalizeTitle(name), SEASONS[season].lower()))
        for title in wanted:
            for item in items:
                if normalizeTitle(item.get('name')) == title:
                    return item['id'], item['name']
        return None, None
    items = (data.get('film') or []) + (data.get('tv') or [])
    item = matchTitle(name, year, [(i.get('name'), i.get('year'), i) for i in items])
    return (item['id'], item['name']) if item else (None, None)


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    wanted = wantedLanguages(lang1, lang2, lang3)
    season = int(season) if tvshow and season else 0
    title_id, found = find_title_id(tvshow or title, year, season)
    log(__name__, "suggest match for '%s' (%s): %s %s" % (tvshow or title, year or season, title_id, found))
    if not title_id:
        return [], "", ""
    r = session.get("%s/subscene/%s" % (MAIN_URL, title_id), timeout=SEARCH_TIMEOUT)
    r.raise_for_status()
    if season:
        this_episode, any_episode, this_season = episodeFilters(season, int(episode))
    episodes, packs, seen = [], [], set()
    for a in BeautifulSoup(r.text, 'html.parser').select('td.a1 a[href^="/subtitle/"]'):
        sub_id = a['href'].rsplit('/', 1)[-1]
        lang = a.select_one('span.l')
        release = a.select_one('span.new')
        if not lang or not release or sub_id in seen:
            continue
        release = release.get_text(' ', strip=True) or "%s (%s)" % (found, sub_id)
        code = langCode(lang.get_text(strip=True))
        if code not in wanted:
            continue
        seen.add(sub_id)
        sub = {'filename': release, 'id': sub_id, 'language_name': wanted[code], 'sync': False}
        if not season or this_episode.search(release):
            episodes.append(sub)
        elif not any_episode.search(release) and this_season.search(release):
            packs.append(sub)  # whole season in one archive
    log(__name__, "%d subtitles, %d season packs" % (len(episodes), len(packs)))
    return episodes + packs, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    r = session.get("%s/download/%s" % (MAIN_URL, sub['id']), timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    return False, sub['language_name'], saveSubtitle(tmp_sub_dir, "sub-scene_%s" % sub['id'], r.content)
