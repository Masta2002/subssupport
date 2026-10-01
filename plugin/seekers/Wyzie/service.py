# -*- coding: utf-8 -*-
# Wyzie Subs API (https://docs.wyzie.io/subs/usage/direct), a free key from https://store.wyzie.io/redeem is required
import os
import re

import requests

from ..seeker import SubtitlesDownloadError, SubtitlesErrors
from ..user_agents import get_api_user_agent
from ..utilities import imdbLookup, languageTranslate, log

API_URL = "https://sub.wyzie.io"
API_TIMEOUT = 20
DOWNLOAD_TIMEOUT = 30

settings_provider = None


def _get(url, params=None, timeout=API_TIMEOUT):
    key = settings_provider.getSetting("Wyzie_API_KEY").strip()
    if not key:
        raise SubtitlesDownloadError(SubtitlesErrors.NO_CREDENTIALS_ERROR, "Wyzie requires an API key")
    params = dict(params or {}, key=key)
    response = requests.get(url, params=params, headers={"User-Agent": get_api_user_agent()}, timeout=timeout)
    if response.status_code in (401, 403):
        raise SubtitlesDownloadError(SubtitlesErrors.INVALID_CREDENTIALS_ERROR, "Wyzie API key rejected")
    return response


def test_credentials():
    response = _get(API_URL + "/search", {"id": "tt0133093", "language": "en"})
    if response.status_code == 429:
        return "Wyzie API key OK, but the daily request limit is reached"
    response.raise_for_status()
    return "Wyzie API key OK"


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    imdb_id = imdbLookup(tvshow or title, None if tvshow else year, bool(tvshow))
    if not imdb_id:
        return [], "", "title not found on IMDb"
    langs = sorted(set(filter(None, (languageTranslate(lang, 0, 2) for lang in (lang1, lang2, lang3) if lang))))
    params = {"id": imdb_id, "language": ",".join("pt" if code == "pb" else code for code in langs), "format": "srt,sub"}
    if tvshow and season and episode:
        params.update({"season": int(season), "episode": int(episode)})
    log(__name__, "search params: %s" % params)
    response = _get(API_URL + "/search", params)
    if response.status_code == 400:  # "No subtitles found"
        return [], "", ""
    response.raise_for_status()

    subtitles_list = []
    for item in response.json():
        if not item.get("url"):
            continue
        code = item.get("language") or ""
        subtitles_list.append({
            "id": item["url"],
            "filename": item.get("release") or item.get("fileName") or item.get("media") or title,
            "language_name": languageTranslate(code, 2, 0) or item.get("display") or code,
            "sync": False,
            "format": item.get("format") or "srt",
            "rating": str(min(10, int(item.get("downloadCount") or 0) // 500 + 1)),
        })
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    subtitle = subtitles_list[pos]
    response = requests.get(subtitle["id"], headers={"User-Agent": get_api_user_agent()}, timeout=DOWNLOAD_TIMEOUT)
    response.raise_for_status()
    if not response.content:
        raise SubtitlesDownloadError(SubtitlesErrors.UNKNOWN_ERROR, "Wyzie returned an empty file")
    if not os.path.isdir(tmp_sub_dir):
        os.makedirs(tmp_sub_dir)
    name = re.sub(r'[\\/:*?"<>|]+', "_", subtitle["filename"])[:120]
    filepath = os.path.join(tmp_sub_dir, "%s.%s" % (name, subtitle["format"]))
    with open(filepath, "wb") as f:
        f.write(response.content)
    return False, subtitle["language_name"], filepath
