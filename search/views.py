from rest_framework.decorators import api_view
from rest_framework import status
from api.sparql_client import run_sparql
from api.views import sparql_to_json
from kagebunshin.common.utils import api_response
from difflib import SequenceMatcher

# pakai run_sparql dari api/sparql_client.py untuk ambil data dari GraphDB
# pakai sparql_to_json dari api/views.py untuk ratain (mempermudah) hasil SPARQL ke JSON biasa
# return dibungkus pake api_response dari kagebunshin/common/utils.py biar konsisten
# jangan lupa bikin .env

@api_view(['GET'])
def get_data(request):
    query = """
    SELECT ?s ?p ?o
    WHERE {
      ?s ?p ?o
    }
    LIMIT 10
    """
    result = run_sparql(query) 

    if "error" in result:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal ambil data", result)
    
    data = sparql_to_json(result)
    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)

def clean_genres(genres_str):
    return [g.strip() for g in genres_str.split(",") if g.strip()]

@api_view(['GET'])
def get_anime(request):
    query = """
    PREFIX v: <http://kagebunshin.org/vocab/>

    SELECT ?anime ?image ?title ?year (GROUP_CONCAT(?genreAll; separator=",") AS ?genres)
    WHERE {
      ?anime v:hasImage ?image ;
             v:hasTitle ?title ;
             v:hasGenre ?genreAll ;
             v:isReleased ?releaseNode .

      OPTIONAL {
        ?releaseNode v:releasedYear ?year .
      }
    }
    GROUP BY ?anime ?image ?title ?year
    """

    result = run_sparql(query)

    if "error" in result:
        return api_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Gagal ambil data",
            result
        )

    data = sparql_to_json(result)
    for item in data:
        if "genres" in item:
            item["genres"] = clean_genres(item["genres"])

    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)

@api_view(['GET'])
def get_anime_by_genre(request):
    genre = request.GET.get("genre", "").strip()

    if not genre:
        return api_response(
            status.HTTP_400_BAD_REQUEST,
            "Parameter 'genre' wajib diisi",
            None
        )

    filter_genre = f"""
    FILTER EXISTS {{
      ?anime v:hasGenre ?g .
      FILTER(LCASE(?g) = LCASE("{genre}"))
    }}
    """

    query = f"""
    PREFIX v: <http://kagebunshin.org/vocab/>

    SELECT ?anime ?image ?title ?year
           (GROUP_CONCAT(?genreAll; separator=",") AS ?genres)
    WHERE {{
      ?anime v:hasImage ?image ;
             v:hasTitle ?title ;
             v:hasGenre ?genreAll ;
             v:isReleased ?releaseNode .

      OPTIONAL {{
        ?releaseNode v:releasedYear ?year .
      }}

      {filter_genre}
    }}
    GROUP BY ?anime ?image ?title ?year
    """

    result = run_sparql(query)

    if "error" in result:
        return api_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Gagal ambil data",
            result
        )

    data = sparql_to_json(result)
    for item in data:
        if "genres" in item:
            item["genres"] = clean_genres(item["genres"])
    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)

def clean_anime(anime_str):
    return [a.strip() for a in anime_str.split(",") if a.strip()]

@api_view(['GET'])
def get_character(request):
    query = """
    PREFIX v: <http://kagebunshin.org/vocab/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?char ?name (GROUP_CONCAT(?title; separator=", ") AS ?animeList)
    WHERE {
      ?anime v:hasCharacter ?char ;
        v:hasTitle ?title .

      ?char foaf:name ?name .
    }
    GROUP BY ?char ?name

    """
    result = run_sparql(query) 

    if "error" in result:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal ambil data", result)
    
    data = sparql_to_json(result)
    for item in data:
      if "animeList" in item:
          item["animeList"] = clean_anime(item["animeList"])
    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)

def rank_results(results, query, field):
    def similarity(a, b):
        return SequenceMatcher(None, a, b).ratio()
    
    ranked_results = []
    q = query.lower()

    for row in results:
        value = row.get(field, "").lower()
        score = similarity(value, q) * 100
        row['score'] = round(score, 2)
        ranked_results.append(row)
    
    ranked_results.sort(key=lambda x: x['score'], reverse=True)
    return ranked_results

def sparql_anime(search):
    filter_title = f'FILTER(CONTAINS(LCASE(?title), LCASE("{search}")))'

    return f"""
    PREFIX v: <http://kagebunshin.org/vocab/>

    SELECT ?anime ?image ?title ?year
           (GROUP_CONCAT(?genreAll; separator=",") AS ?genres)
    WHERE {{
      ?anime v:hasImage ?image ;
             v:hasTitle ?title ;
             v:hasGenre ?genreAll ;
             v:isReleased ?releaseNode .

      OPTIONAL {{
        ?releaseNode v:releasedYear ?year .
      }}

      {filter_title}
    }}
    GROUP BY ?anime ?image ?title ?year
    """

def sparql_anime_by_genre(search, genre):
    filter_title = f'FILTER(CONTAINS(LCASE(?title), LCASE("{search}")))'

    filter_genre = f"""
    FILTER EXISTS {{
      ?anime v:hasGenre ?g .
      FILTER(CONTAINS(LCASE(?g), LCASE("{genre}")))
    }}
    """

    return f"""
    PREFIX v: <http://kagebunshin.org/vocab/>

    SELECT ?anime ?image ?title ?year
           (GROUP_CONCAT(?genreAll; separator=",") AS ?genres)
    WHERE {{
      ?anime v:hasImage ?image ;
             v:hasTitle ?title ;
             v:hasGenre ?genreAll ;
             v:isReleased ?releaseNode .

      OPTIONAL {{
        ?releaseNode v:releasedYear ?year .
      }}

      {filter_title}
      {filter_genre}
    }}
    GROUP BY ?anime ?image ?title ?year
    """

@api_view(['GET'])
def query_anime(request):
    search = request.GET.get("search", "")
    genre = request.GET.get("genre", "")

    if genre:
      query = sparql_anime_by_genre(search, genre)
    else:
      query = sparql_anime(search)

    result = run_sparql(query)

    if "error" in result:
      return api_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "Gagal ambil data",
        result
      )

    data = sparql_to_json(result)
    data = rank_results(data, search, "title")

    for item in data:
        item["genres"] = [g.strip() for g in item["genres"].split(",") if g.strip()]

    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)

@api_view(['GET'])
def query_character(request):
    search = request.GET.get("search", "")

    query = f"""
    PREFIX v: <http://kagebunshin.org/vocab/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?char ?name (GROUP_CONCAT(?title; separator=", ") AS ?animeList)
    WHERE {{
      ?anime v:hasCharacter ?char ;
             v:hasTitle ?title .

      ?char foaf:name ?name .

      FILTER(CONTAINS(LCASE(?name), LCASE("{search}")))
    }}
    GROUP BY ?char ?name
    """

    result = run_sparql(query)

    if "error" in result:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal ambil data", result)
    
    data = sparql_to_json(result)
    data = rank_results(data, search, "name")
    for item in data:
      if "animeList" in item:
          item["animeList"] = clean_anime(item["animeList"])

    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)

# INFO BOX

@api_view(['GET'])
def get_anime_by_pk(request):
    pk = request.GET.get("pk", "").strip()
    if not pk:
        return api_response(status.HTTP_400_BAD_REQUEST, "Parameter 'pk' wajib diisi", None)

    uri = f"http://kagebunshin.org/anime/{pk}"

    query = f"""
    PREFIX v: <http://kagebunshin.org/vocab/>
    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

    SELECT ?anime ?title ?desc ?image ?type ?episodes ?status ?premiered ?duration ?rating ?score ?rank ?popularity ?members ?favorites ?source ?studio
           (GROUP_CONCAT(DISTINCT ?genre; separator=",") AS ?genres)
           (GROUP_CONCAT(DISTINCT ?theme; separator=",") AS ?themes)
           (GROUP_CONCAT(DISTINCT ?producer; separator=",") AS ?producers)
           (GROUP_CONCAT(DISTINCT ?char; separator=",") AS ?characters)
           ?year ?season
    WHERE {{
      VALUES ?anime {{ <{uri}> }}

      OPTIONAL {{ ?anime v:hasTitle ?title . }}
      OPTIONAL {{ ?anime v:hasDesc ?desc . }}
      OPTIONAL {{ ?anime v:hasImage ?image . }}
      OPTIONAL {{ ?anime v:hasType ?type . }}
      OPTIONAL {{ ?anime v:hasEpisodes ?episodes . }}
      OPTIONAL {{ ?anime v:hasStatus ?status . }}
      OPTIONAL {{ ?anime v:isPremiered ?premiered . }}
      OPTIONAL {{ ?anime v:hasDuration ?duration . }}
      OPTIONAL {{ ?anime v:hasRating ?rating . }}
      OPTIONAL {{ ?anime v:hasScore ?score . }}
      OPTIONAL {{ ?anime v:isRanked ?rank . }}
      OPTIONAL {{ ?anime v:isPopularity ?popularity . }}
      OPTIONAL {{ ?anime v:hasMembers ?members . }}
      OPTIONAL {{ ?anime v:hasFavorites ?favorites . }}
      OPTIONAL {{ ?anime v:hasSource ?source . }}
      OPTIONAL {{ ?anime v:hasStudio ?studio . }}
      OPTIONAL {{ ?anime v:hasProducer ?producer . }}
      OPTIONAL {{ ?anime v:hasGenre ?genre . }}
      OPTIONAL {{ ?anime v:hasTheme ?theme . }}
      OPTIONAL {{ ?anime v:hasCharacter ?char . }}

      OPTIONAL {{
        ?anime v:isReleased ?releaseNode .
        OPTIONAL {{ ?releaseNode v:releasedYear ?year . }}
        OPTIONAL {{ ?releaseNode v:releasedSeason ?season . }}
      }}
    }}
    GROUP BY ?anime ?title ?desc ?image ?type ?episodes ?status ?premiered ?duration ?rating ?score ?rank ?popularity ?members ?favorites ?source ?studio ?year ?season
    LIMIT 1
    """

    result = run_sparql(query)
    if "error" in result:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal ambil data anime", result)

    items = sparql_to_json(result)
    if not items:
        return api_response(status.HTTP_404_NOT_FOUND, "Anime tidak ditemukan", None)

    item = items[0]

    def split_field(val):
        return [v.strip() for v in val.split(",") if v.strip()] if val else []

    anime = {
        "uri": item.get("anime"),
        "title": item.get("title"),
        "description": item.get("desc"),
        "image": item.get("image"),
        "type": item.get("type"),
        "episodes": item.get("episodes"),
        "airingStatus": item.get("status"),
        "premiered": item.get("premiered"),
        "duration": item.get("duration"),
        "rating": item.get("rating"),
        "score": item.get("score"),
        "rank": item.get("rank"),
        "popularity": item.get("popularity"),
        "members": item.get("members"),
        "favorites": item.get("favorites"),
        "source": item.get("source"),
        "studio": item.get("studio"),
        "producers": split_field(item.get("producers")),
        "genres": split_field(item.get("genres")),
        "themes": split_field(item.get("themes")),
        "characters": split_field(item.get("characters")),
        "releasedYear": item.get("year"),
        "releasedSeason": item.get("season"),
    }

    return api_response(status.HTTP_200_OK, "Berhasil ambil data anime", anime)

@api_view(['GET'])
def get_character_by_pk(request):
    pk = request.GET.get("pk", "").strip()
    if not pk:
        return api_response(status.HTTP_400_BAD_REQUEST, "Parameter 'pk' wajib diisi", None)

    uri = f"http://kagebunshin.org/character/{pk}"

    query = f"""
    PREFIX v: <http://kagebunshin.org/vocab/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    PREFIX vcard: <http://www.w3.org/2006/vcard/ns#>

    SELECT ?char ?name ?fullName ?altName ?desc ?url
           (GROUP_CONCAT(DISTINCT ?title; separator=", ") AS ?animeList)
    WHERE {{
      VALUES ?char {{ <{uri}> }}

      OPTIONAL {{ ?char foaf:name ?name . }}
      OPTIONAL {{ ?char v:hasFullName ?fullName . }}
      OPTIONAL {{ ?char v:hasAltName ?altName . }}
      OPTIONAL {{ ?char v:hasDescription ?desc . }}
      OPTIONAL {{ ?char vcard:hasURL ?url . }}

      OPTIONAL {{
        ?anime v:hasCharacter ?char ;
               v:hasTitle ?title .
      }}
    }}
    GROUP BY ?char ?name ?fullName ?altName ?desc ?url
    LIMIT 1
    """

    result = run_sparql(query)
    if "error" in result:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal ambil data karakter", result)

    items = sparql_to_json(result)
    if not items:
        return api_response(status.HTTP_404_NOT_FOUND, "Karakter tidak ditemukan", None)

    item = items[0]

    character = {
        "uri": item.get("char"),
        "name": item.get("name"),
        "fullName": item.get("fullName"),
        "altName": item.get("altName"),
        "description": item.get("desc"),
        "url": item.get("url"),
        "animeList": clean_anime(item.get("animeList")) if item.get("animeList") else []
    }

    return api_response(status.HTTP_200_OK, "Berhasil ambil data karakter", character)

@api_view(['GET'])
def get_studio_by_pk(request):
    pk = request.GET.get("pk", "").strip()
    if not pk:
        return api_response(status.HTTP_400_BAD_REQUEST, "Parameter 'pk' wajib diisi", None)

    uri = f"http://kagebunshin.org/studio/{pk}"

    query = f"""
    PREFIX v: <http://kagebunshin.org/vocab/>
    PREFIX vcard: <http://www.w3.org/2006/vcard/ns#>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?studio ?name ?logo ?url
           (GROUP_CONCAT(DISTINCT ?found; separator=",") AS ?founders)
           (GROUP_CONCAT(DISTINCT ?country; separator=",") AS ?originCountries)
           (GROUP_CONCAT(DISTINCT ?anime; separator=",") AS ?animes)
    WHERE {{
      VALUES ?studio {{ <{uri}> }}

      OPTIONAL {{ ?studio foaf:name ?name . }}
      OPTIONAL {{ ?studio vcard:hasLogo ?logo . }}
      OPTIONAL {{ ?studio vcard:hasURL ?url . }}
      OPTIONAL {{ ?studio v:foundedBy ?found . }}
      OPTIONAL {{ ?studio v:hasOriginCountry ?country . }}

      # Cari semua anime yang menunjuk ke studio ini melalui properti v:hasStudio
      OPTIONAL {{ ?anime v:hasStudio ?studio . }}
    }}
    GROUP BY ?studio ?name ?logo ?url
    LIMIT 1
    """

    result = run_sparql(query)
    if "error" in result:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal ambil data studio", result)

    items = sparql_to_json(result)
    if not items:
        return api_response(status.HTTP_404_NOT_FOUND, "Studio tidak ditemukan", None)

    item = items[0]

    def split_field(val):
        return [v.strip() for v in val.split(",") if v.strip()] if val else []

    studio = {
        "uri": item.get("studio"),
        "name": item.get("name"),
        "logo": item.get("logo"),
        "url": item.get("url"),
        "founders": split_field(item.get("founders")),
        "originCountries": split_field(item.get("originCountries")),
        "animeList": split_field(item.get("animes")),
    }

    return api_response(status.HTTP_200_OK, "Berhasil ambil data studio", studio)
