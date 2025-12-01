from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from api.sparql_client import test_connection, run_sparql
from kagebunshin.common.utils import api_response

@api_view(['GET'])
def health(request):
    return Response({"status": "ok"})

@api_view(['GET'])
def test_sparql(request):
    result = test_connection()
    return api_response(status.HTTP_200_OK, "Berhasil connect ke GraphDB", result)

def simplify_bindings(results):
    simplified = []
    for row in results.get("bindings", []):
        item = {}
        for key, val in row.items():
            item[key] = val.get("value")
        simplified.append(item)
    return simplified

def sparql_to_json(result):
    return simplify_bindings(result.get("results", {}))
