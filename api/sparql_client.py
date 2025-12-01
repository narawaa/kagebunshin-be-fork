import os
import requests

GRAPHDB_URL = os.getenv('GRAPHDB_URL')
REPO_NAME = "kagebunshin-graph"

def test_connection():
    url = f"{GRAPHDB_URL}/repositories/{REPO_NAME}/statements"
    try:
        response = requests.head(url)
        response.raise_for_status()
        return {"database": "connected"}
    except Exception as e:
        return {"error": str(e)}

def run_sparql(query: str):
    headers = {
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    try:
        response = requests.post(
            f"{GRAPHDB_URL}/repositories/{REPO_NAME}",
            data={"query": query},
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}
