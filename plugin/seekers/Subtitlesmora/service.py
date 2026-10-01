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

from ..user_agents import get_random_ua
from ..utilities import log

ITEM = "mora25r"
METADATA_URL = "https://archive.org/metadata/%s" % ITEM
DOWNLOAD_URL = "https://archive.org/download/%s/" % ITEM
LANGUAGE = "Arabic"
SUB_EXTS = ('.srt', '.ass', '.ssa', '.sub')
CACHE_DIR = "/var/volatile/tmp" if os.path.isdir("/var/volatile/tmp") else tempfile.gettempdir()
CACHE_FILE = os.path.join(CACHE_DIR, "subssupport_archive_%s.json" % ITEM)
CACHE_TIMEOUT = 24 * 3600

ROMAN = (('xx', 20), ('xix', 19), ('xviii', 18), ('xvii', 17), ('xvi', 16), ('xv', 15), ('xiv', 14), ('xiii', 13),
         ('xii', 12), ('xi', 11), ('x', 10), ('ix', 9), ('viii', 8), ('vii', 7), ('vi', 6), ('v', 5), ('iv', 4),
         ('iii', 3), ('ii', 2))
ROMAN_TO_INT = dict((r, str(n)) for r, n in ROMAN)
INT_TO_ROMAN = dict((str(n), r) for r, n in ROMAN)


def normalize(text):
    """'The Matrix: Reloaded' -> 'the.matrix.reloaded'"""
    text = re.sub(r"['`]", '', text.lower()).replace('&', 'and')
    return '.'.join(re.findall(r'[^\W_]+', text))


def title_variations(title):
    """Title with Roman numerals as digits and vice versa ('rocky.ii' -> 'rocky.2'), 'I' is left alone."""
    words = normalize(title).split('.')
    variations = ['.'.join(words)]
    for table in (ROMAN_TO_INT, INT_TO_ROMAN):
        variant = '.'.join(table.get(w, w) for w in words)
        if variant not in variations:
            variations.append(variant)
    return variations


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
        r = requests.get(METADATA_URL, headers={'User-Agent': get_random_ua()}, timeout=15)
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
    if LANGUAGE not in (lang1, lang2, lang3) or not name or not name.strip():
        return [], "", ""
    episode_tag = ".s%02de%02d." % (int(season), int(episode)) if tvshow else None
    prefixes = [v + '.' for v in title_variations(name)]
    hits, year_hits = [], []
    for filename in get_file_list():
        norm = normalize(filename) + '.'
        if not any(norm.startswith(p) for p in prefixes) or episode_tag and episode_tag not in norm:
            continue
        hits.append(filename)
        if year and '.%s.' % year in norm:
            year_hits.append(filename)
    log(__name__, "%d files match %s (%d with year %s)" % (len(hits), prefixes, len(year_hits), year))
    subtitles_list = [{'filename': os.path.splitext(f)[0], 'id': f, 'language_name': LANGUAGE, 'sync': False}
                      for f in (year_hits or hits)]
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    sub = subtitles_list[pos]
    r = requests.get(DOWNLOAD_URL + quote(sub['id']), headers={'User-Agent': get_random_ua()}, timeout=30)
    r.raise_for_status()
    if not r.content:
        raise Exception("empty subtitle file")
    path = os.path.join(tmp_sub_dir, os.path.basename(sub['id']))
    with open(path, 'wb') as f:
        f.write(r.content)
    return False, sub['language_name'], path
