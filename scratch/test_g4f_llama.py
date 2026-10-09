import g4f
from g4f.client import Client

def test_g4f_llama():
    client = Client()
    try:
        response = client.chat.completions.create(
            model="llama-3-8b", # or "llama-3.1-70b"
            messages=[{"role": "user", "content": "Reply with only valid JSON: {\"hello\": \"world\"}"}],
        )
        print("Success:", response.choices[0].message.content)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_g4f_llama()
