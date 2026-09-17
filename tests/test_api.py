import requests
import sys

BASE_URL = "http://localhost:8000"

def test_endpoint(name, url):
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
    test_endpoint("Health", f"{BASE_URL}/health")
    test_endpoint("Stats", f"{BASE_URL}/api/v1/stats")
    test_endpoint("Jobs", f"{BASE_URL}/api/v1/jobs?limit=5")
    test_endpoint("Businesses", f"{BASE_URL}/api/v1/businesses?limit=5")

if __name__ == "__main__":
    run_tests()
