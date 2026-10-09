from gradio_client import Client

def test_qwen_space():
    print("Connecting to Qwen2.5-72B-Instruct space...")
    client = Client("Qwen/Qwen2.5-72B-Instruct")
    try:
        print("Generating text...")
        # The Qwen space typically takes (query, history, system) as input for the chat interface.
        # Let's inspect the API of the space first if predict fails.
        result = client.predict(
            query="Reply with valid JSON: {\"hello\": \"world\"}",
            history=[],
            system="You are a helpful assistant.",
            api_name="/model_chat"
        )
        print("Result:", result)
    except Exception as e:
        print("Error:", e)
        # If it fails, maybe we can list the endpoints
        print(client.view_api(return_format="dict"))

if __name__ == "__main__":
    test_qwen_space()
