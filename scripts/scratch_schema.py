import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

headers = {}
token = os.getenv("HOMEFY_ADMIN_TOKEN") or ""

def query_schema():
    query = """
    query {
      __type(name: "BillApplicableTo") {
        enumValues {
          name
        }
      }
    }
    """
    graphql_url = os.getenv("HOMEFY_GRAPHQL_URL", "https://api-staging.homefy.co.in/graphql")
    res = requests.post(graphql_url, json={"query": query})
    try:
        data = res.json()
        vals = data.get("data", {}).get("__type", {}).get("enumValues", [])
        for v in vals:
            print(v["name"])
    except Exception as e:
        print("Error", e)

if __name__ == "__main__":
    query_schema()
