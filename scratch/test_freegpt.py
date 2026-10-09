from freegpt import Client

def test_freegpt():
    try:
        print("Testing freeGPT...")
        resp = Client.create_completion("gpt3", "Reply with valid JSON: {\"hello\": \"world\"}")
        print("Success:", resp)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_freegpt()
