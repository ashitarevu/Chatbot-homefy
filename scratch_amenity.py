import requests

url = "https://api-staging.homefy.co.in/graphql"
query = """
query {
  __type(name: "FilterAmenityInput") {
    inputFields { name type { name kind } }
  }
}
"""
response = requests.post(url, json={'query': query})
print(response.json())
