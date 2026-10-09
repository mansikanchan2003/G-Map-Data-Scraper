from gradio_client import Client

def test_qwen_chat():
    try:
        print("Connecting to ATshayu/qwen2.5...")
        client = Client("ATshayu/qwen2.5")
        
        print("API endpoints:")
        print(client.view_api(return_format="dict"))
        
        print("Predicting...")
        result = client.predict(
            message="Reply with only valid JSON: {\"hello\": \"world\"}",
            system_message="You are a helpful assistant.",
            max_tokens=512,
            temperature=0.7,
            top_p=0.95,
            api_name="/chat"
        )
        print("Result:", result)
            
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_qwen_chat()
