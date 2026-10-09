from gradio_client import Client, handle_file
import time

def test_qwen_vl():
    try:
        print("Connecting to Qwen2.5-VL-32B-Instruct...")
        client = Client("Qwen/Qwen2.5-VL-32B-Instruct")
        
        print("Adding text to history...")
        # According to standard Gradio chat interfaces, the prompt goes into the text field.
        # The endpoints were: predict(history, text, api_name="/add_text")
        
        history = client.predict(
            history=[],
            text="Reply with only valid JSON: {\"hello\": \"world\"}",
            api_name="/add_text"
        )
        
        print("Generating response...")
        # The generation endpoint: predict(_chatbot, api_name="/predict")
        result = client.predict(
            _chatbot=history,
            api_name="/predict"
        )
        
        print("Result type:", type(result))
        print("Result length:", len(result))
        # result is a list of [user_message, bot_message]
        if result and len(result) > 0:
            print("Response:", result[-1][1])
        else:
            print("Empty result:", result)
            
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_qwen_vl()
