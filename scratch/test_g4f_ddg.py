import g4f
from g4f.Provider import DuckDuckGo

def test_g4f_ddg():
    try:
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4o_mini,
            provider=DuckDuckGo,
            messages=[{"role": "user", "content": "Reply with only valid JSON: {\"hello\": \"world\"}"}],
        )
        print("Success:", response)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_g4f_ddg()
