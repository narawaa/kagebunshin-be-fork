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
