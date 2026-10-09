from gradio_client import Client

def test_qwen_text():
    try:
        print("Connecting to Qwen2.5-VL-32B-Instruct...")
        client = Client("Qwen/Qwen2.5-VL-32B-Instruct")
        
        print("Adding text...")
        history = client.predict(
            history=[],
            text="Reply with only valid JSON: {\"hello\": \"world\"}",
            api_name="/add_text"
        )
        
        print("Predicting...")
        result = client.predict(
            _chatbot=history,
            api_name="/predict"
        )
        # The result is typically the updated history
        print("Result:")
        # The last message is usually the response
        if result and len(result) > 0:
            print(result[-1][1])
        else:
            print(result)
            
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_qwen_text()
