from rest_framework.decorators import api_view
from rest_framework import status
from api.sparql_client import run_sparql
from api.views import sparql_to_json
from kagebunshin.common.utils import api_response
from difflib import SequenceMatcher
import requests
import re
from difflib import SequenceMatcher
import requests
import json

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

@api_view(['GET'])
def query_all(request):
    search = request.GET.get("search", "")

    query = f"""
    PREFIX v: <http://kagebunshin.org/vocab/>
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>
    PREFIX vcard: <http://www.w3.org/2006/vcard/ns#>

    SELECT DISTINCT 
        ?resource
        ?typeLabel
        ?title
        ?image
        ?fullName

    WHERE {{
      VALUES ?prop {{
        v:hasTitle
        v:hasDesc
        v:hasImage
        v:hasType
        v:hasStatus
        v:hasSource
        v:hasGenre
        v:hasTheme
        v:hasStudio
        v:hasProducer
        v:hasRating
        v:hasCharacter
        v:hasDemographic

        vcard:hasURL
        foaf:name
        v:hasAltName
        v:hasDescription
        v:hasFullName
        v:hasAttributes
      }}

      ?resource ?prop ?value .

      FILTER(CONTAINS(LCASE(STR(?value)), LCASE("{search}")))
        
      OPTIONAL {{ ?resource v:hasTitle ?title . }}
      OPTIONAL {{ ?resource v:hasImage ?image . }}

      OPTIONAL {{ ?resource v:hasFullName ?fullName . }} 
      
      BIND(
        IF(BOUND(?title), "anime",
          IF(BOUND(?fullName), "character", "unknown")
        ) AS ?typeLabel
      )
    }}
    """

    result = run_sparql(query)

    if "error" in result:
        return api_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal ambil data", result)
    
    data = sparql_to_json(result)

    return api_response(status.HTTP_200_OK, "Berhasil ambil data", data)

def clean_anime(anime_str):
    return [a.strip() for a in anime_str.split(",") if a.strip()]

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
    PREFIX foaf: <http://xmlns.com/foaf/0.1/>

        SELECT ?anime ?title ?desc ?image ?type ?episodes ?status ?premiered ?duration ?rating ?score ?rank ?popularity ?members ?favorites ?source ?studio
          (GROUP_CONCAT(DISTINCT ?genre; separator=",") AS ?genres)
          (GROUP_CONCAT(DISTINCT ?theme; separator=",") AS ?themes)
          (GROUP_CONCAT(DISTINCT ?producer; separator=",") AS ?producers)
          (GROUP_CONCAT(DISTINCT STR(?char); separator=",") AS ?charactersUri)
          (GROUP_CONCAT(DISTINCT COALESCE(?charName, ""); separator=",") AS ?charactersName)
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
      OPTIONAL {{ ?char v:hasFullName ?charName . }}

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
        "charactersUri": split_field(item.get("charactersUri")),
        "charactersName": split_field(item.get("charactersName")),
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

    SELECT ?char ?name ?fullName ?altName ?desc ?url ?attributes
      (GROUP_CONCAT(DISTINCT ?title; separator=", ") AS ?animeList)
    WHERE {{
      VALUES ?char {{ <{uri}> }}

      OPTIONAL {{ ?char foaf:name ?name . }}
      OPTIONAL {{ ?char v:hasFullName ?fullName . }}
      OPTIONAL {{ ?char v:hasAltName ?altName . }}
      OPTIONAL {{ ?char v:hasDescription ?desc . }}
      OPTIONAL {{ ?char vcard:hasURL ?url . }}
      OPTIONAL {{ ?char v:hasAttributes ?attributes . }}

      OPTIONAL {{
        ?anime v:hasCharacter ?char ;
               v:hasTitle ?title .
      }}
    }}
    GROUP BY ?char ?name ?fullName ?altName ?desc ?url ?attributes
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
        "attributes": [],
        "url": item.get("url"),
        "animeList": clean_anime(item.get("animeList")) if item.get("animeList") else []
    }

    # Parse attributes field if present. Expecting a JSON array string like:
    # "[{\"name\": \"Birthday\", \"value\": \"August 23\"}, ...]"
    raw_attrs = item.get("attributes")
    if raw_attrs:
      parsed = []
      try:
        parsed_json = json.loads(raw_attrs)
        if isinstance(parsed_json, list):
          parsed = parsed_json
        elif isinstance(parsed_json, dict):
          parsed = [parsed_json]
      except Exception:
        # try to be more permissive: replace single quotes with double quotes
        try:
          cleaned = raw_attrs.replace("'", '"')
          parsed_json = json.loads(cleaned)
          if isinstance(parsed_json, list):
            parsed = parsed_json
          elif isinstance(parsed_json, dict):
            parsed = [parsed_json]
        except Exception:
          # last resort: attempt to extract key/value pairs with regex
          try:
            pairs = re.findall(r'\{[^}]*\}', raw_attrs)
            for p in pairs:
              # remove enclosing braces and split by commas
              body = p.strip('{}')
              attrs = {}
              for part in re.split(r',\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', body):
                kv = part.split(':', 1)
                if len(kv) == 2:
                  k = kv[0].strip().strip('"\'')
                  v = kv[1].strip().strip('"\'')
                  attrs[k] = v
              if attrs:
                parsed.append(attrs)
          except Exception:
            parsed = []

      character["attributes"] = parsed

    return api_response(status.HTTP_200_OK, "Berhasil ambil data karakter", character)

@api_view(['GET'])
def get_studio_wd_by_name(request, pk: str = None):
    """Lookup a studio on Wikidata by name extracted from the URL path segment `pk`.

      Example URL path: `/search/studio/wd/Toei_Animation/` -> studio name `Toei Animation`.
      Returns notable works (P800), founders (P112), country (P17), official website (P856) and logo (P154).
      """
    if not pk:
      pk = (request.GET.get('pk') or '').strip()

    if not pk:
      return api_response(status.HTTP_400_BAD_REQUEST, "Parameter 'pk' (studio name) wajib diisi pada query param '?pk=...'", None)

    # Normalize underscores to spaces and sanitize double quotes
    studio_name = pk.replace('_', ' ').strip()
    studio_name_escaped = studio_name.replace('"', '\\"')

    query = f"""
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX wikibase: <http://wikiba.se/ontology#>
    PREFIX bd: <http://www.bigdata.com/rdf#>

    SELECT DISTINCT
      ?studio ?studioLabel
      (GROUP_CONCAT(DISTINCT ?notableWorkLabel; separator=", ") AS ?notableWorks)
      (GROUP_CONCAT(DISTINCT ?foundedByLabel; separator=", ") AS ?founders)
      ?countryLabel
      ?officialWebsite
      ?logo
    WHERE {{
      ?studio rdfs:label "{studio_name_escaped}"@en .

      OPTIONAL {{ ?studio wdt:P800 ?notableWork . ?notableWork rdfs:label ?notableWorkLabel FILTER(LANG(?notableWorkLabel) = "en") }}
      OPTIONAL {{ ?studio wdt:P112 ?foundedBy . ?foundedBy rdfs:label ?foundedByLabel FILTER(LANG(?foundedByLabel) = "en") }}
      OPTIONAL {{ ?studio wdt:P17 ?country . ?country rdfs:label ?countryLabel FILTER(LANG(?countryLabel) = "en") }}
      OPTIONAL {{ ?studio wdt:P856 ?officialWebsite . }}
      OPTIONAL {{ ?studio wdt:P154 ?logo . }}

      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en".
        ?studio rdfs:label ?studioLabel .
      }}
    }}
    GROUP BY
      ?studio ?studioLabel
      ?countryLabel ?officialWebsite ?logo
    LIMIT 1
    """

    url = 'https://query.wikidata.org/sparql'
    headers = {'Accept': 'application/sparql-results+json', 'User-Agent': 'kagebunshin-be/1.0 (contact: dev@example.com)'}
    try:
      resp = requests.get(url, params={'query': query}, headers=headers, timeout=15)
    except Exception as e:
      return api_response(status.HTTP_502_BAD_GATEWAY, 'Gagal menghubungi Wikidata', {'error': str(e)})

    if resp.status_code != 200:
      return api_response(status.HTTP_502_BAD_GATEWAY, 'Wikidata returned non-200', {'status_code': resp.status_code, 'text': resp.text[:200]})

    body = resp.json()
    bindings = body.get('results', {}).get('bindings', [])
    if not bindings:
      return api_response(status.HTTP_404_NOT_FOUND, 'Studio Wikidata tidak ditemukan', None)

    b = bindings[0]

    def read(binding, key):
      v = binding.get(key)
      if not v:
        return None
      return v.get('value')

    notable_raw = read(b, 'notableWorks') or ''
    founders_raw = read(b, 'founders') or ''

    data = {
      'wikidataUri': read(b, 'studio'),
      'name': read(b, 'studioLabel') or studio_name,
      'notableWorks': [s for s in notable_raw.split('||') if s],
      'founders': [s for s in founders_raw.split('||') if s],
      'originCountry': read(b, 'countryLabel'),
      'officialWebsite': read(b, 'officialWebsite'),
      'logo': read(b, 'logo'),
    }

    # Also try to find anime in the local GraphDB tagged with the same studio
    # We construct a likely local studio URI by replacing spaces with underscores
    # e.g. studio_name "Toei Animation" -> http://kagebunshin.org/studio/Toei_Animation
    local_studio_fragment = studio_name.replace(' ', '_')
    local_studio_uri = f"http://kagebunshin.org/studio/{local_studio_fragment}"

    local_query = f"""
    PREFIX v: <http://kagebunshin.org/vocab/>

    SELECT ?anime ?title
    WHERE {{
      VALUES ?studio {{ <{local_studio_uri}> }}
      ?anime v:hasStudio ?studio .
      OPTIONAL {{ ?anime v:hasTitle ?title . }}
    }}
    """

    local_anime = []
    try:
      local_result = run_sparql(local_query)
      if "error" not in local_result:
        local_items = sparql_to_json(local_result)
        for it in local_items:
          local_anime.append({
            'uri': it.get('anime'),
            'title': it.get('title')
          })
    except Exception as e:
      # ignore local lookup errors but include empty list
      local_anime = []

    data['localAnime'] = local_anime

    return api_response(status.HTTP_200_OK, 'Berhasil ambil data dari Wikidata (by name)', data)
