from hugchat import hugchat

def test_hugchat():
    try:
        print("Testing hugchat...")
        chatbot = hugchat.ChatBot(cookie_path=None) # Maybe works without login?
        response = chatbot.chat("Reply with valid JSON: {\"hello\": \"world\"}")
        print("Success:", response)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_hugchat()
