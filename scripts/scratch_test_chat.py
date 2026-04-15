import requests
import json

url = "http://127.0.0.1:5000/api/chat"
# Use a random session ID
data = {
    "message": "show all amenities",
    "session_id": "test_amenity_session"
}
res = requests.post(url, json=data)
print(res.json())
