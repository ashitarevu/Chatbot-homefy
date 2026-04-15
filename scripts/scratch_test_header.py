import requests
import json
import os

url = "https://api-staging.homefy.co.in/graphql"
# To test this, I need that exact Bearer token the user got. But I can't get it unless I login.
# Could it be I just need to add apartment-id to headers for amenity_api.py?
