import os
from dotenv import load_dotenv
import auth
from api_handler import HomefyAPIHandler
import json

load_dotenv()
handler = HomefyAPIHandler()

phone = "9876543210"
otp = "123456" # Dev OTP is usually 123456 or we can just call verify_otp if it's static in auth.py

print("1. Sending OTP...")
resp = auth.send_otp(phone)
print(resp)
if "result" in resp: temp_token = resp["result"].get("token")
else: temp_token = resp.get("token")

print("2. Verifying OTP...", temp_token[:10] if temp_token else None)
veri = auth.verify_otp("123456", temp_token)
print(veri)
if "access_token" in veri:
    access_token = veri["access_token"]
    
    print("3. Getting apartments...")
    apts = handler.get_my_apartments(access_token)
    print("Aparts:", len(apts.get("myApartments", [])))
    
    # Find Ishriha 
    req_id = None
    for a in apts.get("myApartments", []):
        if "Ishriha" in a.get("name", ""):
            req_id = a["requests"][0]["id"]
            break
            
    if req_id:
        print("4. Getting Ishriha user token for request", req_id)
        tk_resp = handler.get_access_token(req_id, temp_token)
        real_token = tk_resp.get("accessToken", {}).get("token")
        
        print("5. Querying all_amenities with token", real_token[:10] if real_token else None)
        q = handler._load_gql("graphql/amenities/queries/all_amenities.graphql")
        amenities = handler.execute_graphql(q, {"filter": {}}, real_token)
        print(json.dumps(amenities, indent=2))
    else:
        print("Could not find Ishriha request.")
else:
    print("OTP failed.")
