from rest_framework.decorators import api_view
from rest_framework import status
from api.sparql_client import run_sparql
from api.views import sparql_to_json
from kagebunshin.common.utils import api_response
from difflib import SequenceMatcher
import re

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

def str_to_list(str):
    return [s.strip() for s in str.split(",") if s.strip()]

@api_view(['GET'])
def get_anime(request):
    query = """
    PREFIX v: <http://kagebunshin.org/vocab/>

    SELECT ?anime ?image ?title ?year (GROUP_CONCAT(DISTINCT ?themeAll; separator=",") AS ?themes)
    WHERE {
      ?anime v:hasImage ?image ;
             v:hasTitle ?title ;
             v:hasTheme ?themeAll ;
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
        if "themes" in item:
            item["themes"] = str_to_list(item["themes"])

    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)

@api_view(['GET'])
def get_anime_by_theme(request):
    theme = request.GET.get("theme", "").strip()

    if not theme:
        return api_response(
            status.HTTP_400_BAD_REQUEST,
            "Parameter 'theme' wajib diisi",
            None
        )

    filter_theme = f"""
    FILTER EXISTS {{
      ?anime v:hasTheme ?t .
      FILTER(LCASE(?t) = LCASE("{theme}"))
    }}
    """

    query = f"""
    PREFIX v: <http://kagebunshin.org/vocab/>

    SELECT ?anime ?image ?title ?year
           (GROUP_CONCAT(DISTINCT ?themeAll; separator=",") AS ?themes)
    WHERE {{
      ?anime v:hasImage ?image ;
             v:hasTitle ?title ;
             v:hasTheme ?themeAll ;
             v:isReleased ?releaseNode .

      OPTIONAL {{
        ?releaseNode v:releasedYear ?year .
      }}

      {filter_theme}
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
        if "themes" in item:
            item["themes"] = str_to_list(item["themes"])
    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)

@api_view(['GET'])
def get_character(request):
    query = """
    PREFIX v: <http://kagebunshin.org/vocab/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?char ?name (GROUP_CONCAT(DISTINCT ?title; separator=", ") AS ?animeList)
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
          item["animeList"] = str_to_list(item["animeList"])
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

def sparql_anime(filter_title):
    return f"""
    PREFIX v: <http://kagebunshin.org/vocab/>

    SELECT ?anime ?image ?title ?year
           (GROUP_CONCAT(DISTINCT ?themeAll; separator=",") AS ?themes)
    WHERE {{
      ?anime v:hasImage ?image ;
             v:hasTitle ?title ;
             v:hasTheme ?themeAll ;
             v:isReleased ?releaseNode .

      OPTIONAL {{
        ?releaseNode v:releasedYear ?year .
      }}

      {filter_title}
    }}
    GROUP BY ?anime ?image ?title ?year
    """

def sparql_anime_by_theme(filter_title, theme):
    filter_theme = f"""
    FILTER EXISTS {{
      ?anime v:hasTheme ?t .
      FILTER(CONTAINS(LCASE(?t), LCASE("{theme}")))
    }}
    """

    return f"""
    PREFIX v: <http://kagebunshin.org/vocab/>

    SELECT ?anime ?image ?title ?year
           (GROUP_CONCAT(DISTINCT ?themeAll; separator=",") AS ?themes)
    WHERE {{
      ?anime v:hasImage ?image ;
             v:hasTitle ?title ;
             v:hasTheme ?themeAll ;
             v:isReleased ?releaseNode .

      OPTIONAL {{
        ?releaseNode v:releasedYear ?year .
      }}

      {filter_title}
      {filter_theme}
    }}
    GROUP BY ?anime ?image ?title ?year
    """

@api_view(['GET'])
def query_anime(request):
    search = request.GET.get("search", "")
    theme = request.GET.get("theme", "")

    # Token search
    normalized = re.sub(r"[^a-zA-Z0-9 ]+", " ", search.lower()).strip()
    tokens = [t for t in normalized.split() if t]

    # No space search
    search_no_space = re.sub(r"[^a-zA-Z0-9]+", "", search.lower()).strip()

    token_filters = "\n".join(
        [f'FILTER(CONTAINS(REPLACE(LCASE(?title), "[^a-z0-9]", ""), "{token}"))'
         for token in tokens]
    ) if tokens else ""

    exact_filter = ""
    if search_no_space and " " not in search:
        exact_filter = f'''
        FILTER(CONTAINS(
            REPLACE(LCASE(?title), "[^a-z0-9]", ""), 
            "{search_no_space}"
        ))
        '''
    
    all_filters = token_filters + "\n" + exact_filter

    if theme:
      query = sparql_anime_by_theme(all_filters, theme)
    else:
      query = sparql_anime(all_filters)

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
        item["themes"] = [g.strip() for g in item["themes"].split(",") if g.strip()]

    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)

@api_view(['GET'])
def query_character(request):
    search = request.GET.get("search", "")

    # Token search
    normalized = re.sub(r"[^a-zA-Z0-9 ]+", " ", search.lower()).strip()
    tokens = [t for t in normalized.split() if t]

    # No space search
    search_no_space = re.sub(r"[^a-zA-Z0-9]+", "", search.lower()).strip()

    token_filters = "\n".join(
        [f'FILTER(CONTAINS(REPLACE(LCASE(?fullName), "[^a-z0-9]", ""), "{token}"))'
         for token in tokens]
    ) if tokens else ""

    exact_filter = ""
    if search_no_space and " " not in search:
        exact_filter = f'''
        FILTER(CONTAINS(
            REPLACE(LCASE(?fullName), "[^a-z0-9]", ""), 
            "{search_no_space}"
        ))
        '''

    all_filters = token_filters + "\n" + exact_filter

    query = f"""
    PREFIX v: <http://kagebunshin.org/vocab/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

    SELECT ?char ?name (GROUP_CONCAT(DISTINCT ?title; separator=", ") AS ?animeList)
    WHERE {{
      ?anime v:hasCharacter ?char ;
             v:hasTitle ?title .

      ?char foaf:name ?name ;
            v:hasFullName ?fullName .

      {all_filters}
    }}
    GROUP BY ?char ?name ?fullName
    """

    result = run_sparql(query)

    if "error" in result:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal ambil data", result)
    
    data = sparql_to_json(result)
    data = rank_results(data, search, "name")

    for item in data:
        if "animeList" in item:
            item["animeList"] = str_to_list(item["animeList"])

    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)
