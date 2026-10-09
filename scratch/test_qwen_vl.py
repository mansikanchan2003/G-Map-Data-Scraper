from gradio_client import Client

def test_qwen_vl():
    try:
        print("Connecting to Qwen2.5-VL-32B-Instruct...")
        # VL model needs text and image. For text-only, we might just pass text.
        client = Client("Qwen/Qwen2.5-VL-32B-Instruct")
        print("API endpoints:")
        print(client.view_api(return_format="dict"))
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_qwen_vl()
