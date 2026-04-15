import os
import sys
import json

# Add root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api_handler import HomefyAPIHandler

def test_meeting_details():
    handler = HomefyAPIHandler()
    token = os.getenv("HOMEFY_AUTH_TOKEN")
    meeting_id = "cmnh69gc602syp8e2d33jamlw"
    
    print(f"Fetching details for meeting: {meeting_id}...")
    details = handler._q_get_detailed_meeting(token, meeting_id)
    print(json.dumps(details, indent=2))

if __name__ == "__main__":
    test_meeting_details()
