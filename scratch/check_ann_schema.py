
import requests
import json
import os

URL = "https://api-staging.homefy.co.in/graphql"
TOKEN = "YOUR_TOKEN_HERE" # I'll need a real token or I'll just check the schema without it if public

query = """
{
  __type(name: "AnnouncementFilterInput") {
    inputFields {
      name
      type {
        name
        kind
      }
    }
  }
}
"""

def check_schema():
    response = requests.post(URL, json={'query': query})
    print(json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    check_schema()
