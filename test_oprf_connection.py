import requests
import sys

try:
    response = requests.get('http://localhost:8080/status')
    print("OPRF Service Status:", response.status_code)
    if response.ok:
        print(response.json())
        sys.exit(0)
    else:
        print("Failed to connect:", response.text)
        sys.exit(1)
except Exception as e:
    print("Error connecting to OPRF service:", e)
    sys.exit(1) 