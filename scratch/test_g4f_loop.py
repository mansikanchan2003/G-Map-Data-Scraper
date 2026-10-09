import g4f

def test_all_providers():
    working = []
    # g4f.Provider.__all__ contains the list of providers
    for provider_name in g4f.Provider.__all__:
        try:
            provider = getattr(g4f.Provider, provider_name)
            if not provider.working:
                continue
            print(f"Testing {provider_name}...")
            response = g4f.ChatCompletion.create(
                model=g4f.models.gpt_4o_mini, # or try default
                messages=[{"role": "user", "content": "Reply exactly: OK"}],
                provider=provider,
            )
            print(f"  Success! {provider_name} returned: {response}")
            working.append(provider_name)
            break
        except Exception as e:
            # print(f"  Failed: {e}")
            pass
            
    if working:
        print("Found working providers:", working)
    else:
        print("None worked.")

if __name__ == "__main__":
    test_all_providers()
