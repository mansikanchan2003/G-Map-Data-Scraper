import requests
import sys

models = [
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "stabilityai/stable-diffusion-3.5-large",
    "prompthero/openjourney"
]

def test_models():
    for model in models:
        url = f"https://api-inference.huggingface.co/models/{model}"
        payload = {"inputs": "A beautiful sunset"}
        try:
            response = requests.post(url, json=payload, headers={})
            print(f"Model {model}: {response.status_code}")
            if response.status_code == 200:
                print("Success!")
            else:
                print(response.text)
        except Exception as e:
            print(f"Error {model}: {e}")

if __name__ == "__main__":
    test_models()
