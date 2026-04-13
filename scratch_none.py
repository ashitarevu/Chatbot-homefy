import requests
import json

url = "https://api-staging.homefy.co.in/graphql"
# We need an admin or a user. Since I can't receive OTP, I can try to find an existing token.
# Let's read chatbot.auth_tokens if possible from a running instance? No, impossible.
# Let's use the UI. Wait, I can print the error from execute_graphql!
