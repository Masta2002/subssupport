# -*- coding: UTF-8 -*-
# OpenSubtitles.com REST API, see https://opensubtitles.stoplight.io/docs/opensubtitles-api
import os

import requests

from ..seeker import SubtitlesDownloadError, SubtitlesErrors
from ..user_agents import get_api_user_agent
from ..utilities import languageTranslate, hashFile, log

API_URL = "https://api.opensubtitles.com/api/v1"
API_TIMEOUT = 15
DOWNLOAD_TIMEOUT = 30

# our iso639-1 codes -> OpenSubtitles language codes
OS_LANG_CODES = {"pb": "pt-br", "pt": "pt-pt", "zh": "zh-cn"}

settings_provider = None
_token = {}  # (api_key, username) -> (token, api_url)


def _api_key():
    key = settings_provider.getSetting("OpenSubtitles_API_KEY").strip()
    if not key:
        raise SubtitlesDownloadError(SubtitlesErrors.NO_CREDENTIALS_ERROR, "OpenSubtitles.com requires an API key")
    return key


def _headers(api_key, token=None):
    headers = {"Api-Key": api_key, "User-Agent": get_api_user_agent(), "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer %s" % token
    return headers


def login(force=False):
    """Returns (token, api_url), token is None when no username/password is set."""
    api_key = _api_key()
    username = settings_provider.getSetting("OpenSubtitles_username").strip()
    password = settings_provider.getSetting("OpenSubtitles_password")
    if not username or not password:
        return None, API_URL
    cache_key = (api_key, username)
    if not force and cache_key in _token:
        return _token[cache_key]
    response = requests.post(API_URL + "/login", json={"username": username, "password": password}, headers=_headers(api_key), timeout=API_TIMEOUT)
    if response.status_code in (400, 401, 403):
        raise SubtitlesDownloadError(SubtitlesErrors.INVALID_CREDENTIALS_ERROR, "OpenSubtitles.com login failed")
    response.raise_for_status()
    data = response.json()
    base_url = data.get("base_url")  # VIP accounts get their own api host
    api_url = "https://%s/api/v1" % base_url if base_url else API_URL
    _token[cache_key] = (data.get("token"), api_url)
    return _token[cache_key]


def test_credentials():
    token, api_url = login(force=True)
    url = api_url + "/infos/user" if token else API_URL + "/infos/formats"
    response = requests.get(url, headers=_headers(_api_key(), token), timeout=API_TIMEOUT)
    if response.status_code in (401, 403):
        raise SubtitlesDownloadError(SubtitlesErrors.INVALID_CREDENTIALS_ERROR, "OpenSubtitles.com API key rejected")
    response.raise_for_status()
    if not token:
        return "API key OK (no username/password set, downloads are limited)"
    data = response.json().get("data", {})
    return "Login OK, downloads left today: %s/%s" % (data.get("remaining_downloads", "?"), data.get("allowed_downloads", "?"))


def _lang_code(name):
    code = languageTranslate(name, 0, 2)
    return OS_LANG_CODES.get(code, code)


def _lang_name(code):
    code = "pb" if code == "pt-br" else code.split("-")[0]
    return languageTranslate(code, 2, 0) or code


def search_subtitles(file_original_path, title, tvshow, year, season, episode, set_temp, rar, lang1, lang2, lang3, stack):
    api_key = _api_key()
    langs = sorted(set(filter(None, (_lang_code(lang) for lang in (lang1, lang2, lang3) if lang))))
    params = {"languages": ",".join(langs)}
    if tvshow:
        params.update({"query": tvshow, "type": "episode"})
        if season:
            params["season_number"] = int(season)
        if episode:
            params["episode_number"] = int(episode)
    else:
        params.update({"query": title, "type": "movie"})
        if year:
            params["year"] = int(year)
    if file_original_path and os.path.isfile(file_original_path):
        try:
            params["moviehash"] = hashFile(file_original_path, rar)[1]
        except Exception as e:
            log(__name__, "hash calculation failed: %s" % e)
    # the API answers with a redirect unless the parameters are lowercase and sorted
    params = sorted((k, str(v).lower()) for k, v in params.items())
    log(__name__, "search params: %s" % params)
    response = requests.get(API_URL + "/subtitles", params=params, headers=_headers(api_key), timeout=API_TIMEOUT)
    if response.status_code in (401, 403):
        raise SubtitlesDownloadError(SubtitlesErrors.INVALID_CREDENTIALS_ERROR, "OpenSubtitles.com API key rejected")
    response.raise_for_status()

    subtitles_list = []
    for item in response.json().get("data", []):
        attributes = item.get("attributes", {})
        files = attributes.get("files") or []
        if not files:
            continue
        downloads = int(attributes.get("download_count") or 0)
        subtitles_list.append({
            "id": files[0]["file_id"],
            "filename": attributes.get("release") or files[0].get("file_name") or title,
            "language_name": _lang_name(attributes.get("language") or ""),
            "sync": bool(attributes.get("moviehash_match")),
            "rating": str(min(10, downloads // 50 + 1)),
            "no_files": len(files),
        })
    subtitles_list.sort(key=lambda s: (not s["sync"], -int(s["rating"])))
    return subtitles_list, "", ""


def download_subtitles(subtitles_list, pos, zip_subs, tmp_sub_dir, sub_folder, session_id):
    api_key = _api_key()
    subtitle = subtitles_list[pos]
    token, api_url = login()
    payload = {"file_id": subtitle["id"]}
    response = requests.post(api_url + "/download", json=payload, headers=_headers(api_key, token), timeout=API_TIMEOUT)
    if response.status_code == 401 and token:  # expired token
        token, api_url = login(force=True)
        response = requests.post(api_url + "/download", json=payload, headers=_headers(api_key, token), timeout=API_TIMEOUT)
    if response.status_code == 406:  # daily download quota used up
        raise SubtitlesDownloadError(SubtitlesErrors.UNKNOWN_ERROR, response.json().get("message", "download limit reached"))
    response.raise_for_status()
    data = response.json()
    log(__name__, "remaining downloads: %s" % data.get("remaining"))
    content = requests.get(data["link"], headers={"User-Agent": get_api_user_agent()}, timeout=DOWNLOAD_TIMEOUT)
    content.raise_for_status()
    filename = os.path.basename(data.get("file_name") or "%s.srt" % subtitle["id"])
    if not os.path.isdir(tmp_sub_dir):
        os.makedirs(tmp_sub_dir)
    filepath = os.path.join(tmp_sub_dir, filename)
    with open(filepath, "wb") as f:
        f.write(content.content)
    return False, subtitle["language_name"], filepath
