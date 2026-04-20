
import requests
import json

URL = "https://api-staging.homefy.co.in/graphql"
query = """
{
  __type(name: "Announcement") {
    fields {
      name
      type {
        name
        kind
      }
    }
  }
}
"""

def check_announcement_fields():
    response = requests.post(URL, json={'query': query})
    print(json.dumps(response.json(), indent=2))

if __name__ == "__main__":
    check_announcement_fields()
