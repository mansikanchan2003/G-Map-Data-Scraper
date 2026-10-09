from gradio_client import Client

def test_llama_space():
    print("Connecting to Llama-3.2-Vision space...")
    try:
        client = Client("huggingface-projects/llama-3.2-vision-instruct")
        print("API endpoints:")
        print(client.view_api(return_format="dict"))
        
        print("Generating text...")
        result = client.predict(
            message={"text": "Reply with only valid JSON: {\"hello\": \"world\"}", "files": []},
            system_prompt="You are a helpful assistant.",
            temperature=0.7,
            max_new_tokens=100,
            api_name="/chat"
        )
        print("Result:", result)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_llama_space()
