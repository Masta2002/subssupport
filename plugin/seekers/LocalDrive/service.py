# -*- coding: utf-8 -*-
# Finds subtitles in the configured search path and next to the played video file
import os
import re

from ..utilities import languageTranslate, log, saveSubtitle, yearMatch

SUBTITLE_EXTENSIONS = (".srt", ".sub", ".ass", ".ssa")
MAX_DEPTH = 3

settings_provider = None


def _words(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def _language(filename):
    """Language code in front of the extension, i.e. movie.en.srt / movie_ara.srt"""
    m = re.search(r"[._ -]([a-z]{2,3}(?:-[a-z]{2})?)$", os.path.splitext(filename)[0], re.I)
    if m:
        code = m.group(1).lower()
        for idx in (2, 3):
            name = languageTranslate(code, idx, 0)
            if name:
                return name
    return ""


def _walk(path):
    base_depth = path.rstrip(os.sep).count(os.sep)
    for root, dirs, files in os.walk(path):
        if root.count(os.sep) - base_depth >= MAX_DEPTH:
            dirs[:] = []
        for name in files:
            if name.lower().endswith(SUBTITLE_EXTENSIONS):
                yield root, name


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    paths = []
    search_path = settings_provider.getSetting("LocalSearchPath").strip()
    if search_path and os.path.isdir(search_path):
        paths.append(search_path)
    if file_original_path and os.path.isfile(file_original_path):
        paths.append(os.path.dirname(file_original_path))
    title_words = _words(tvshow or title or "")
    if not title_words:
        return [], "", ""
    episode_tag = "s%02de%02d" % (int(season), int(episode)) if tvshow and season and episode else ""
    langs = [lang for lang in (lang1, lang2, lang3) if lang]

    subtitles_list = []
    seen = set()
    for path in paths:
        for root, name in _walk(path):
            filepath = os.path.join(root, name)
            if filepath in seen:
                continue
            words = _words(name)
            joined = "".join(words)
            if not all(w in words for w in title_words) or (episode_tag and episode_tag not in joined):
                continue
            found_year = re.search(r"(?:19|20)\d{2}", name)
            if not tvshow and found_year and not yearMatch(found_year.group(0), year):
                continue
            language = _language(name)
            if language and langs and language not in langs:
                continue
            seen.add(filepath)
            subtitles_list.append({
                "filename": name,
                "path": filepath,
                "language_name": language or (langs[0] if langs else "English"),
                "sync": False,
            })
    log(__name__, "found %d local subtitles in %s" % (len(subtitles_list), paths))
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    subtitle = subtitles_list[pos]
    with open(subtitle["path"], "rb") as f:
        filepath = saveSubtitle(tmp_sub_dir, subtitle["filename"], f.read())
    return False, subtitle["language_name"], filepath
