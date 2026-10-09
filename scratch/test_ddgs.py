from duckduckgo_search import DDGS

def test_ddgs_chat():
    try:
        print("Initializing DDGS...")
        # Models can be 'gpt-4o-mini', 'claude-3-haiku', 'llama-3.1-70b', 'mixtral-8x7b'
        results = DDGS().chat("Reply with valid JSON: {\"hello\": \"world\"}", model='llama-3.1-70b')
        print("Success:", results)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_ddgs_chat()
