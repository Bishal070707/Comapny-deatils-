#!/usr/bin/env python
import requests
import json
import sys

try:
    url = "http://localhost:8000/send"
    data = {
        "recipient": "sayancr799@gmail.com",
        "subject": "Test Email",
        "template": "reminder",
        "name": "Admin"
    }
    
    print("Sending request to:", url)
    print("Payload:", json.dumps(data, indent=2))
    print("-" * 50)
    
    response = requests.post(url, json=data, timeout=5)
    
    print("Status Code:", response.status_code)
    print("Response Headers:", dict(response.headers))
    print("Response Body:")
    print(json.dumps(response.json(), indent=2))
    
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    sys.exit(1)
