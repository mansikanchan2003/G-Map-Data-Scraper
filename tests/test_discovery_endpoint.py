import requests
import json
import time

BASE_URL = "http://localhost:8000"

def run_discovery():
    print("Triggering controlled discovery test for 1 job...")
    response = requests.post(f"{BASE_URL}/api/v1/discovery/batch", json={"batch_size": 1, "delay_between_jobs_seconds": 1})
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

if __name__ == "__main__":
    run_discovery()
