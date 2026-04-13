import requests
import json
import os

url = "https://api-staging.homefy.co.in/graphql"
# The token is usually obtained via app login, I'll need some token. Wait, if I don't have a token, it will be unauthorized.
# The user's app runs and hits INTERNAL_SERVER_ERROR probably WITH a token.
# Does it hit 500 without a token?
# Let's test unauthenticated request first to see if it's a structural schema 500.

query = """
query AllAmenities($filter: FilterAmenityInput) {
  allAmenities(filter: $filter) {
    data {
      id
      name
    }
  }
}
"""

res = requests.post(url, json={"query": query, "variables": {"filter": {}}})
print("Result without token:", res.json())
