import g4f

def test_g4f():
    try:
        response = g4f.ChatCompletion.create(
            model=g4f.models.gpt_4o_mini,
            messages=[{"role": "user", "content": "Reply with only valid JSON: {\"hello\": \"world\"}"}],
        )
        print("Success:", response)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_g4f()
