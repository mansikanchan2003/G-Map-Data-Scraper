import sys
try:
    from duckai import DuckAI
except ImportError:
    print("Could not import DuckAI")
    sys.exit(1)

def test_duckai():
    try:
        print("Initializing DuckAI...")
        client = DuckAI()
        response = client.chat("Reply with valid JSON: {\"hello\": \"world\"}", model="gpt-4o-mini")
        print("Success:", response)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_duckai()
