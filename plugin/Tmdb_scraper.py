import random
import re
import time

import requests
from bs4 import BeautifulSoup


DEBUG = False
TMDB_URL = "https://www.themoviedb.org"

user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.2 Mobile/15E148 Safari/604.1",
]


def _log(msg, error=False):
    if error or DEBUG:
        print("[TMDB] %s" % msg)


def build_headers():
    return {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9,ar-EG;q=0.8,ar;q=0.7",
        "Referer": TMDB_URL,
        "Connection": "keep-alive",
    }


def _get_soup(url, context, params=None, timeout=10):
    try:
        response = requests.get(url, params=params, headers=build_headers(), timeout=timeout)
        _log("GET %s -> %s (%s)" % (response.url, response.status_code, context))
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        _log("%s failed: %s - %s" % (context, url, e), True)
        return None


def _movie_link(card):
    return card.select_one('a[href^="/movie/"]') or card.select_one('a[href^="/tv/"]') or card.find("a", class_="result")


def extract_title_from_card(card):
    title_span = card.select_one("h2 span")
    if title_span and title_span.get_text(strip=True):
        return title_span.get_text(strip=True)

    for tag in (card.find("h2"), _movie_link(card)):
        if tag:
            for span in tag.find_all("span", class_="title"):
                span.decompose()
            title = tag.get_text(strip=True)
            if title:
                return title

    img_tag = card.find("img", class_="poster")
    if img_tag and img_tag.has_attr("alt"):
        return img_tag["alt"]

    a_tag = _movie_link(card)
    if a_tag and a_tag.has_attr("href"):
        url_parts = a_tag["href"].split("/")
        if len(url_parts) > 2:
            title_part = url_parts[-1]
            if "-" in title_part:
                title_part = title_part.split("-", 1)[1]
            return title_part.replace("-", " ").title()
    return "Unknown Title"


def extract_alternative_title(card):
    alt_title_span = card.find("span", class_="title")
    return alt_title_span.get_text(strip=True) if alt_title_span else None


def extract_poster_url(card):
    img_tag = card.find("img", class_="poster")
    if not img_tag or not img_tag.has_attr("src"):
        return None
    poster_url = img_tag["src"]
    for old in ("w94_and_h141_bestv2", "w130_and_h195_bestv2", "w94_and_h141_face", "w188_and_h282_face"):
        if old in poster_url:
            return poster_url.replace(old, "w220_and_h330_face")
    return poster_url


def extract_tmdb_id(card):
    a_tag = _movie_link(card)
    if a_tag and a_tag.has_attr("href"):
        match = re.search(r"/(?:movie|tv)/(\d+)", a_tag["href"])
        if match:
            return match.group(1)
    return None


def scrape_tmdb_movies(movie_title):
    soup = _get_soup(TMDB_URL + "/search", "search", params={"query": movie_title})
    if soup is None:
        return []
    # one card list per section (movies, tv, collections), the section order varies
    movie_cards = soup.select("div.media-card-list div.comp\\:media-card")
    _log("found %d results for %s" % (len(movie_cards), movie_title))

    movies_data = []
    for index, card in enumerate(movie_cards, 1):
        try:
            a_tag = card.select_one('a[href^="/movie/"]') or card.select_one('a[href^="/tv/"]')
            if not a_tag:
                continue
            movie = {"title": extract_title_from_card(card)}

            alt_title = extract_alternative_title(card)
            if alt_title:
                movie["alternative_title"] = alt_title
            if a_tag and a_tag.has_attr("href"):
                movie["url"] = TMDB_URL + a_tag["href"]

            release_date = card.select_one("span.release_date")
            if release_date:
                movie["release_date"] = release_date.get_text(" ", strip=True)

            overview_p = card.select_one("div p")
            if overview_p and overview_p.get_text(" ", strip=True):
                movie["overview"] = overview_p.get_text(" ", strip=True)

            poster_url = extract_poster_url(card)
            if poster_url:
                movie["poster_url"] = poster_url
            if a_tag and a_tag.has_attr("data-media-type"):
                movie["media_type"] = a_tag["data-media-type"]
            if a_tag and a_tag.has_attr("data-media-adult"):
                movie["adult_content"] = a_tag["data-media-adult"] == "true"

            tmdb_id = extract_tmdb_id(card)
            if tmdb_id:
                movie["tmdb_id"] = tmdb_id
            movies_data.append(movie)
        except Exception as e:
            _log("cannot parse result %d: %s" % (index, e), True)
    movies_data.sort(key=lambda movie: "/movie/" not in movie.get("url", ""))  # movies first
    return movies_data


def scrape_movie_images(movie_url, kind, size):
    """Image urls of one kind (logos, backdrops, posters) in the given size."""
    time.sleep(0.5)
    soup = _get_soup("%s/images/%s" % (movie_url, kind), kind)
    section = soup and soup.find("section", class_="panel user_images")
    if not section:
        return []
    return [img["src"] for img in section.select('img[src*="%s"]' % size) if img.has_attr("src")]


def scrape_movie_trailers(movie_url):
    time.sleep(0.5)
    soup = _get_soup(movie_url + "/videos?active_nav_item=Trailers", "trailers")
    section = soup and soup.find("section", class_="panel video")
    if not section:
        return []

    trailers = []
    for element in section.find_all("div", class_="video card default"):
        trailer = {}
        play_button = element.find("a", class_="play_trailer")
        if play_button and play_button.has_attr("data-id"):
            trailer["youtube_id"] = play_button["data-id"]
            trailer["youtube_url"] = "https://www.youtube.com/watch?v=%s" % play_button["data-id"]
        if play_button and play_button.has_attr("data-site"):
            trailer["site"] = play_button["data-site"]
        for key, tag, cls in (("title", "h2", None), ("details", "h3", "sub"), ("channel", "h4", None)):
            found = element.find(tag, class_=cls) if cls else element.find(tag)
            if found:
                trailer[key] = found.get_text(strip=True)
        if trailer:
            trailers.append(trailer)
    return trailers


def scrape_movie_cast(movie_url):
    time.sleep(0.5)
    soup = _get_soup(movie_url + "/cast", "cast")
    section = soup and soup.find("section", class_="panel pad")
    if not section:
        return []

    cast = []
    for element in section.find_all("li", attrs={"data-order": True})[:6]:
        actor = {}
        name = element.select_one("div.info p a")
        if name:
            actor["name"] = name.get_text(strip=True)
        character = element.find("p", class_="character")
        if character:
            actor["character"] = character.get_text(strip=True)
        profile_img = element.find("img", class_="profile")
        if profile_img and profile_img.has_attr("src"):
            actor["profile_url"] = profile_img["src"].replace("w66_and_h66_face", "w132_and_h132_face")
        if actor.get("name"):
            cast.append(actor)
    return cast


def scrape_movie_details(movie_url):
    soup = _get_soup(movie_url, "details")
    if soup is None:
        return None
    try:
        details = {}
        for key, tag, cls in (("title", "h2", "title"), ("tagline", "h3", "tagline"), ("release_date", "span", "release"), ("runtime", "span", "runtime")):
            found = soup.find(tag, class_=cls)
            if found:
                details[key] = found.get_text(strip=True)
        title = "title" not in details and soup.select_one("div.title h2")
        if title:
            for span in title.find_all("span"):  # release year
                span.decompose()
            details["title"] = title.get_text(" ", strip=True)

        overview = soup.find("div", class_="overview")
        if overview:
            details["overview"] = (overview.find("p") or overview).get_text(strip=True)

        genres = soup.find("span", class_="genres")
        if genres:
            details["genres"] = [genre.get_text(strip=True) for genre in genres.find_all("a")]

        rating = soup.find("div", class_="user_score_chart")
        if rating and rating.has_attr("data-percent"):
            details["rating"] = rating["data-percent"]

        poster = soup.find("img", class_="poster")
        if poster and poster.has_attr("src"):
            details["poster_url"] = poster["src"]

        for key, kind, size in (("logo_urls", "logos", "w500"), ("backdrop_urls", "backdrops", "w500_and_h282_face"), ("additional_poster_urls", "posters", "w220_and_h330_face")):
            images = scrape_movie_images(movie_url, kind, size)
            if images:
                details[key] = images

        trailers = scrape_movie_trailers(movie_url)
        if trailers:
            details["trailers"] = trailers
        cast = scrape_movie_cast(movie_url)
        if cast:
            details["cast"] = cast

        for person in soup.select("ol.people li.profile"):
            job = person.find("p", class_="job")
            if job and "director" in job.get_text(strip=True).lower():
                name = person.find("p", class_="name")
                if name:
                    details["director"] = (name.find("a") or name).get_text(strip=True)
                break
        return details
    except Exception as e:
        _log("cannot parse details %s: %s" % (movie_url, e), True)
        return None
