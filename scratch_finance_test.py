import os
import json
import sqlite3
from dotenv import load_dotenv

load_dotenv()

from modules.finance.finance_api import FinanceMixin
from modules.base.api_client import BaseAPIClient

class TestClient(BaseAPIClient, FinanceMixin):
    pass

def main():
    client = TestClient()
    
    # We need a token. We can find one in chatbot's state if we search for it
    # No, it's easier to just pick one from the text file or assume we can grab one.
    pass

if __name__ == "__main__":
    main()

