# -*- coding: utf-8 -*-
# SubDL API (https://subdl.com/api-doc), a free API key is required
import os
import re
from urllib.parse import quote_plus

import requests

from ..seeker import SubtitlesDownloadError, SubtitlesErrors
from ..user_agents import get_api_user_agent, get_random_ua
from ..utilities import languageTranslate, log

SEARCH_URL = "https://api.subdl.com/api/v1/subtitles"
DOWNLOAD_URL = "https://dl.subdl.com"
API_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

# our iso639-1 codes -> SubDL language codes
SUBDL_LANG_CODES = {"pb": "BR_PT"}

settings_provider = None


def _api_key():
    key = settings_provider.getSetting("Subdl_API_KEY").strip()
    if not key:
        raise SubtitlesDownloadError(SubtitlesErrors.NO_CREDENTIALS_ERROR, "SubDL requires an API key")
    return key


def _lang_code(name):
    code = languageTranslate(name, 0, 2)
    return SUBDL_LANG_CODES.get(code, (code or "").upper())


def _lang_name(item):
    code = (item.get("language") or "").lower()
    if code == "br_pt":
        code = "pb"
    return languageTranslate(code, 2, 0) or (item.get("lang") or "").capitalize()


def _search(params):
    params["api_key"] = _api_key()
    params["subs_per_page"] = 30
    response = requests.get(SEARCH_URL, params=params, headers={"User-Agent": get_api_user_agent()}, timeout=API_TIMEOUT)
    data = response.json()
    if response.status_code == 403 or data.get("error") == "not_authorized":
        raise SubtitlesDownloadError(SubtitlesErrors.INVALID_CREDENTIALS_ERROR, "SubDL API key rejected")
    if not data.get("status"):
        log(__name__, "search failed: %s" % (data.get("error") or data.get("message")))
        return []
    return data.get("subtitles") or []


def test_credentials():
    _search({"film_name": "The Matrix", "type": "movie", "languages": "EN"})
    return "SubDL API key OK"


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    langs = []
    for lang in (lang1, lang2, lang3):
        code = lang and _lang_code(lang)
        if code and code not in langs:
            langs.append(code)
    params = {"languages": ",".join(langs)}
    if tvshow:
        params.update({"film_name": tvshow, "type": "tv"})
        if season:
            params["season_number"] = int(season)
        if episode:
            params["episode_number"] = int(episode)
    else:
        params.update({"film_name": re.sub(r"\s*\(\d{4}\)$", "", title), "type": "movie"})
        if year:
            params["year"] = year
    log(__name__, "search params: %s" % params)

    subtitles_list = []
    for item in _search(params):
        if not item.get("url"):
            continue
        name = item.get("release_name") or item.get("name") or title
        if tvshow and item.get("full_season"):
            name = "[S%02d] %s" % (int(item.get("season") or 0), name)
        subtitles_list.append({
            "id": item["url"],
            "filename": name,
            "language_name": _lang_name(item),
            "sync": False,
            "author": item.get("author"),
        })
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    subtitle = subtitles_list[pos]
    url = DOWNLOAD_URL + subtitle["id"]
    api_key = _api_key()
    # the cdn serves free keys only for some url forms, try them in order
    attempts = [url, re.sub(r"\.(zip|rar)$", "", url), "%s?api_key=%s" % (url, quote_plus(api_key))]
    headers = {"User-Agent": get_random_ua(), "Accept": "*/*"}
    content = None
    for attempt in attempts:
        try:
            response = requests.get(attempt, headers=headers, timeout=DOWNLOAD_TIMEOUT)
        except requests.RequestException as e:
            log(__name__, "download %s failed: %s" % (attempt, e))
            continue
        if response.status_code == 200 and response.content:
            content = response.content
            break
        log(__name__, "download %s: HTTP %s" % (attempt, response.status_code))
    if content is None:
        raise SubtitlesDownloadError(SubtitlesErrors.UNKNOWN_ERROR, "SubDL download failed")
    if not os.path.isdir(tmp_sub_dir):
        os.makedirs(tmp_sub_dir)
    filepath = os.path.join(tmp_sub_dir, os.path.basename(subtitle["id"]) or "subdl.zip")
    with open(filepath, "wb") as f:
        f.write(content)
    return False, subtitle["language_name"], filepath
