# -*- coding: utf-8 -*-
# SubSource API (https://subsource.net/api-docs), an API key from the user profile page is required
import os
import re

import requests

from ..seeker import SubtitlesDownloadError, SubtitlesErrors
from ..user_agents import get_api_user_agent
from ..utilities import languageTranslate, log

API_URL = "https://api.subsource.net/api/v1"
API_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

# our language names -> SubSource language names
SUBSOURCE_LANGS = {"Persian": "farsi_persian", "PortugueseBrazil": "brazillian_portuguese", "Portuguese (Brazil)": "brazillian_portuguese"}

settings_provider = None


def _get(path, params=None, timeout=API_TIMEOUT):
    key = settings_provider.getSetting("SubSource_API_KEY").strip()
    if not key:
        raise SubtitlesDownloadError(SubtitlesErrors.NO_CREDENTIALS_ERROR, "SubSource requires an API key")
    headers = {"X-API-Key": key, "User-Agent": get_api_user_agent(), "Accept": "application/json"}
    response = requests.get(API_URL + path, params=params, headers=headers, timeout=timeout)
    if response.status_code in (401, 403):
        raise SubtitlesDownloadError(SubtitlesErrors.INVALID_CREDENTIALS_ERROR, "SubSource API key rejected")
    response.raise_for_status()
    return response


def test_credentials():
    _get("/movies/search", {"searchType": "text", "q": "The Matrix"})
    return "SubSource API key OK"


def _lang_param(name):
    return SUBSOURCE_LANGS.get(name, name.lower().replace(" ", "_"))


def _lang_name(lang):
    name = lang.replace("_", " ").title()
    if name == "Farsi Persian":
        name = "Persian"
    return languageTranslate(languageTranslate(name, 0, 2), 2, 0) or name


def _episode_match(release, season, episode):
    m = re.search(r"S(\d{1,2})[ ._-]?E(\d{1,3})", release, re.I) or re.search(r"\b(\d{1,2})x(\d{2,3})\b", release)
    if not m:
        return True  # season pack or unknown naming
    return int(m.group(1)) == int(season) and int(m.group(2)) == int(episode)


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    query = tvshow or re.sub(r"\s*\(\d{4}\)$", "", title)
    params = {"searchType": "text", "q": query, "type": "tvseries" if tvshow else "movie"}
    if year:
        params["year"] = year
    if tvshow and season:
        params["season"] = int(season)
    movies = _get("/movies/search", params).json().get("data") or []
    if not tvshow and year:  # prefer exact year matches
        movies = [m for m in movies if str(m.get("releaseYear")) == str(year)] or movies
    langs = ",".join(sorted(set(_lang_param(lang) for lang in (lang1, lang2, lang3) if lang)))

    subtitles_list = []
    for movie in movies[:3]:
        if tvshow and season and movie.get("season") not in (None, int(season)):
            continue
        params = {"movieId": movie["movieId"], "language": langs, "limit": 100, "sort": "newest"}
        for item in _get("/subtitles", params).json().get("data") or []:
            releases = item.get("releaseInfo") or [movie.get("title") or query]
            if tvshow and episode and not any(_episode_match(r, season, episode) for r in releases):
                continue
            subtitles_list.append({
                "id": item["subtitleId"],
                "filename": releases[0],
                "language_name": _lang_name(item.get("language") or ""),
                "sync": False,
                "rating": str(min(10, int(item.get("downloads") or 0) // 50 + 1)),
            })
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    subtitle = subtitles_list[pos]
    response = _get("/subtitles/%s/download" % subtitle["id"], timeout=DOWNLOAD_TIMEOUT)
    if not response.content:
        raise SubtitlesDownloadError(SubtitlesErrors.UNKNOWN_ERROR, "SubSource returned an empty file")
    if not os.path.isdir(tmp_sub_dir):
        os.makedirs(tmp_sub_dir)
    filepath = os.path.join(tmp_sub_dir, "subsource_%s.zip" % subtitle["id"])
    with open(filepath, "wb") as f:
        f.write(response.content)
    return False, subtitle["language_name"], filepath
