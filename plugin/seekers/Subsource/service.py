# -*- coding: utf-8 -*-
# SubSource API (https://subsource.net/api-docs), an API key from the user profile page is required
import requests

from ..seeker import SubtitlesDownloadError, SubtitlesErrors
from ..user_agents import get_api_user_agent
from ..utilities import downloadRating, episodeFilters, langCode, languageTranslate, saveSubtitle, stripYear, \
    wantedLanguages, yearMatch

API_URL = "https://api.subsource.net/api/v1"
API_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

# our iso639-1 codes -> SubSource language names (others are the lower case english name)
SUBSOURCE_LANGS = {'pt-br': 'brazillian_portuguese', 'fa': 'farsi_persian', 'es': 'spanish', 'zh': 'chinese',
                   'sr': 'serbian', 'bs': 'bosnian'}

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


def _lang_param(code):
    return SUBSOURCE_LANGS.get(code) or languageTranslate(code, 2, 0).lower().replace(" ", "_")


def _lang_name(lang):
    """'farsi_persian' -> 'Persian'"""
    code = langCode(lang.replace("_", " "))
    return languageTranslate(code, 2, 0) if code else lang.replace("_", " ").title()


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    query = tvshow or stripYear(title)
    params = {"searchType": "text", "q": query, "type": "tvseries" if tvshow else "movie"}
    if year:
        params["year"] = year
    if tvshow and season:
        params["season"] = int(season)
    movies = _get("/movies/search", params).json().get("data") or []
    if not tvshow and year:  # prefer matching years
        movies = [m for m in movies if yearMatch(m.get("releaseYear"), year)] or movies
    langs = ",".join(sorted(_lang_param(code) for code in wantedLanguages(lang1, lang2, lang3)))
    if tvshow and season and episode:
        this_episode, any_episode = episodeFilters(int(season), int(episode))[:2]

    subtitles_list = []
    for movie in movies[:3]:
        if tvshow and season and movie.get("season") not in (None, int(season)):
            continue
        params = {"movieId": movie["movieId"], "language": langs, "limit": 100, "sort": "newest"}
        for item in _get("/subtitles", params).json().get("data") or []:
            releases = item.get("releaseInfo") or [movie.get("title") or query]
            # keep this episode, season packs and unknown naming
            if tvshow and season and episode and not any(this_episode.search(r) or not any_episode.search(r) for r in releases):
                continue
            subtitles_list.append({
                "id": item["subtitleId"],
                "filename": releases[0],
                "language_name": _lang_name(item.get("language") or ""),
                "sync": False,
                "rating": downloadRating(item.get("downloads")),
            })
    subtitles_list.sort(key=lambda s: -int(s["rating"]))
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    subtitle = subtitles_list[pos]
    response = _get("/subtitles/%s/download" % subtitle["id"], timeout=DOWNLOAD_TIMEOUT)
    filepath = saveSubtitle(tmp_sub_dir, "subsource_%s" % subtitle["id"], response.content)
    return False, subtitle["language_name"], filepath
