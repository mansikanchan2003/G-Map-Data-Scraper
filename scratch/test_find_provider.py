import g4f

def test_all():
    working = []
    # Test only a few known fast text providers that are usually free
    providers = ["DDG", "DuckDuckGo", "Liaobots", "FreeGpt", "You", "Blackbox", "HuggingChat"]
    
    for name in g4f.Provider.__all__:
        if name in providers or "Chat" in name or "AI" in name or "Gpt" in name:
            try:
                print(f"Testing {name}...")
                provider = getattr(g4f.Provider, name)
                response = g4f.ChatCompletion.create(
                    model=g4f.models.gpt_4o_mini,
                    messages=[{"role": "user", "content": "Reply exactly: OK"}],
                    provider=provider,
                )
                print(f"Success! {name} returned: {response}")
                working.append(name)
                # Test another model to be sure
                resp2 = g4f.ChatCompletion.create(
                    model="llama-3.1-70b",
                    messages=[{"role": "user", "content": "Reply exactly: OK"}],
                    provider=provider,
                )
                print(f"Llama 3.1 70B Success! {name} returned: {resp2}")
                break
            except Exception as e:
                pass
                
    print("Working:", working)

if __name__ == "__main__":
    test_all()
