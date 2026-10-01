"""
Manual smoke check against a running backend: python scripts/smoke_api.py

Lived in tests/ as test_api.py, where pytest collected its helper as a test
and failed on the missing "name" fixture. Everything but /health needs a
session now, so expect 401s there unless the cookie is supplied.
"""
import requests

BASE_URL = "http://localhost:8000"

def check_endpoint(name, url):
    print(f"Testing {name}...")
    try:
        response = requests.get(url)
        print(f"  Status Code: {response.status_code}")
        if response.status_code == 200:
            print("  Response:", str(response.json())[:200] + "..." if len(str(response.json())) > 200 else response.json())
        else:
            print("  Error:", response.text)
    except Exception as e:
        print(f"  Exception: {e}")

def run_tests():
    print("--- API VALIDATION ---")
    check_endpoint("Health", f"{BASE_URL}/health")
    check_endpoint("Stats", f"{BASE_URL}/api/v1/stats")
    check_endpoint("Jobs", f"{BASE_URL}/api/v1/jobs?limit=5")
    check_endpoint("Businesses", f"{BASE_URL}/api/v1/businesses?limit=5")

if __name__ == "__main__":
    run_tests()
