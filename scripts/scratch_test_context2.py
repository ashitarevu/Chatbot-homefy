import os
from api_handler import HomefyAPIHandler

# Try to get the user token from env or a dummy
token = os.getenv("HOMEFY_AUTH_TOKEN", "")

handler = HomefyAPIHandler()
# Directly run the _q_all_amenities function!
print("All Amenities:")
try:
    res1 = handler._q_all_amenities(token, "")
    print(res1)
except Exception as e:
    print("CRASH1", e)

print("\nMy Bookings:")
try:
    res2 = handler._q_my_bookings(token)
    print(res2)
except Exception as e:
    print("CRASH2", e)
