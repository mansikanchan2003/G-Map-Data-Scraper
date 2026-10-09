import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from dotenv import load_dotenv
load_dotenv()

from huggingface_hub import InferenceClient

def test_hf_llm():
    token = os.environ.get("HF_TOKEN")
    client = InferenceClient("Qwen/Qwen2.5-72B-Instruct", token=token)
    prompt = "Reply with only valid JSON: {\"hello\": \"world\"}"
    try:
        response = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100
        )
        print("Success:", response.choices[0].message.content)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_hf_llm()
