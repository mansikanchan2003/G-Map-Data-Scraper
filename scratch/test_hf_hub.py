import os
from huggingface_hub import InferenceClient
from dotenv import load_dotenv

load_dotenv()

client = InferenceClient(api_key=os.environ.get("HF_TOKEN"))

try:
    print("Testing text_to_image...")
    image = client.text_to_image(
        "A cinematic shot of a futuristic city at sunset, neon lights",
        model="black-forest-labs/FLUX.1-schnell"
    )
    image.save("test_hf_hub.png")
    print("Saved test_hf_hub.png")
except Exception as e:
    print(f"Error: {e}")
