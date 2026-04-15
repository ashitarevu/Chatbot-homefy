import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def find_apartment():
    query = """
    query {
      myProfile {
        requests {
          apartment {
            id
            name
          }
        }
      }
    }
    """
    graphql_url = os.getenv("HOMEFY_GRAPHQL_URL", "https://api-staging.homefy.co.in/graphql")
    token = os.getenv("HOMEFY_AUTH_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    res = requests.post(graphql_url, json={"query": query}, headers=headers)
    print(json.dumps(res.json(), indent=2))

if __name__ == "__main__":
    find_apartment()
