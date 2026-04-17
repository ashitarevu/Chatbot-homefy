import os
import requests
from dotenv import load_dotenv

load_dotenv()

REST_BASE_URL = os.getenv("HOMEFY_REST_BASE_URL")
TIMEOUT = 10


def send_otp(phone_number: str) -> dict:
    """
    Step 1: Send OTP to phone number.
    Returns the temporary token needed for verification.
    """
    url = f"{REST_BASE_URL}/otp/send"
    payload = {
        "countryCode": "+91",
        "mobile": phone_number
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json()  # Expected to contain 'token'
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                err_data = e.response.json()
                if "error" in err_data and "message" in err_data["error"]:
                    error_msg = err_data["error"]["message"]
                elif "message" in err_data:
                    error_msg = err_data["message"]
            except Exception:
                pass
        return {"error": error_msg}

def verify_otp(otp_code: str, temp_token: str) -> dict:
    """
    Step 2: Verify the OTP using the code and temporary token.
    Returns the initial JWT token for the user.
    """
    url = f"{REST_BASE_URL}/otp/verify"
    payload = {
        "code": otp_code,
        "token": temp_token
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        
        # API returns: { result: { access_token: "..." } }
        access_token = (
            data.get("result", {}).get("access_token")
            or data.get("result", {}).get("token")
            or data.get("access_token")
            or data.get("token")
        )
        if access_token:
            return {"access_token": access_token}
        else:
            return {"error": f"access_token not found in verify_otp response. Full payload: {data}"}
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                err_data = e.response.json()
                if "error" in err_data and "message" in err_data["error"]:
                    error_msg = err_data["error"]["message"]
                elif "message" in err_data:
                    error_msg = err_data["message"]
            except Exception:
                pass
        return {"error": error_msg}
