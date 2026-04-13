import requests

url = "https://api-staging.homefy.co.in/graphql"
query = """
query {
  __schema {
    queryType {
      fields {
        name
      }
    }
  }
}
"""
response = requests.post(url, json={'query': query})
data = response.json()
fields = data.get("data", {}).get("__schema", {}).get("queryType", {}).get("fields", [])
names = [f["name"] for f in fields]

amen_queries = [n for n in names if "amenit" in n.lower()]
print("AMENITY QUERIES:", amen_queries)
