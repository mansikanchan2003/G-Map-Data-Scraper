from huggingface_hub import InferenceClient

def test_hf_no_token():
    # Let's try some models that are often free and open without token
    models = [
        "Qwen/Qwen2.5-Coder-32B-Instruct",
        "meta-llama/Llama-3.2-3B-Instruct",
        "microsoft/Phi-3-mini-4k-instruct"
    ]
    for m in models:
        try:
            print(f"Testing {m}...")
            client = InferenceClient(m)
            response = client.chat_completion(
                messages=[{"role": "user", "content": "Reply exactly: OK"}],
                max_tokens=10
            )
            print("Success:", response.choices[0].message.content)
            break
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    test_hf_no_token()
