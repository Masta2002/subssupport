# -*- coding: utf-8 -*-
"""Arabic subtitles from the archive.org item "mora25r" (one .srt per movie, a few episodes).

The file list is read from the archive.org metadata API and cached for 24 hours;
titles are matched with Roman numeral variations (Rocky II <-> Rocky 2).
"""
import json
import os
import re
import tempfile
import time
from urllib.parse import quote

import requests

from ..utilities import createSession, log, normalizeTitle, romanVariations, saveSubtitle, wantedLanguages, yearMatch

ITEM = "mora25r"
METADATA_URL = "https://archive.org/metadata/%s" % ITEM
DOWNLOAD_URL = "https://archive.org/download/%s/" % ITEM
LANGUAGE = "Arabic"
SUB_EXTS = ('.srt', '.ass', '.ssa', '.sub')
CACHE_FILE = os.path.join(tempfile.gettempdir(), "subssupport_archive_%s.json" % ITEM)
CACHE_TIMEOUT = 24 * 3600
SEARCH_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

session = createSession()


def normalize(text):
    """'The Matrix: Reloaded' -> 'the.matrix.reloaded'"""
    return normalizeTitle(text).replace(' ', '.')


def read_cache():
    try:
        with open(CACHE_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def get_file_list():
    try:
        fresh = time.time() - os.path.getmtime(CACHE_FILE) < CACHE_TIMEOUT
    except OSError:
        fresh = False
    names = read_cache() if fresh else None
    if names is not None:
        return names
    try:
        r = session.get(METADATA_URL, timeout=SEARCH_TIMEOUT)
        r.raise_for_status()
        names = [f['name'] for f in r.json().get('files', []) if f.get('name', '').lower().endswith(SUB_EXTS)]
    except (requests.RequestException, ValueError) as e:
        log(__name__, "metadata request failed: %s" % e)
        return read_cache() or []  # an outdated list is better than none
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(names, f)
    except OSError as e:
        log(__name__, "cannot write cache %s: %s" % (CACHE_FILE, e))
    return names


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    name = tvshow or title
    if 'ar' not in wantedLanguages(lang1, lang2, lang3) or not name or not name.strip():
        return [], "", ""
    episode_tag = ".s%02de%02d." % (int(season), int(episode)) if tvshow else None
    prefixes = ['.'.join(words) + '.' for words in romanVariations(normalize(name).split('.'))]
    hits, year_hits = [], []
    for filename in get_file_list():
        norm = normalize(filename) + '.'
        if not any(norm.startswith(p) for p in prefixes) or episode_tag and episode_tag not in norm:
            continue
        hits.append(filename)
        if year and any(yearMatch(y, year) for y in re.findall(r'\.((?:19|20)\d\d)(?=\.)', norm)):
            year_hits.append(filename)
    log(__name__, "%d files match %s (%d with year %s)" % (len(hits), prefixes, len(year_hits), year))
    subtitles_list = [{'filename': os.path.splitext(f)[0], 'id': f, 'language_name': LANGUAGE, 'sync': False}
                      for f in (year_hits or hits)]
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    r = session.get(DOWNLOAD_URL + quote(sub['id']), timeout=DOWNLOAD_TIMEOUT)
    r.raise_for_status()
    return False, sub['language_name'], saveSubtitle(tmp_sub_dir, sub['id'], r.content)
