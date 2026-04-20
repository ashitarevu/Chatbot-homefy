
import requests
import json

URL = "https://api-staging.homefy.co.in/graphql"

query = """
{
  __schema {
    queryType {
      fields {
        name
      }
    }
  }
}
"""

def check_queries():
    response = requests.post(URL, json={'query': query})
    fields = response.json().get("data", {}).get("__schema", {}).get("queryType", {}).get("fields", [])
    names = [f["name"] for f in fields]
    for name in names:
        if "nnouncement" in name:
            print(name)

if __name__ == "__main__":
    check_queries()
