import os
import sys
from dotenv import load_dotenv
from webapp.llm import LLMClient

# Load environment
load_dotenv()


def test_connection(name, api_key, base_url, model):
    print(f"\n--- Testing {name} ---")
    print(f"URL: {base_url}")
    print(f"Model: {model}")

    client = LLMClient()
    # Force initialization
    try:
        client.initialize_client(api_key=api_key, base_url=base_url, model=model)

        # Simple test query
        response = client.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Say 'Connection Successful'"}],
            max_tokens=10,
        )
        content = response.choices[0].message.content
        print(f"✅ Success! Response: {content}")
        return True
    except Exception as e:
        print(f"❌ Failed: {e}")
        return False


def main():
    print("Beginning LLM Connection Verification...")

    # 1. Test OpenAI (Cloud)
    # Using the key from environment
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and openai_key.startswith("sk-"):
        test_connection("OpenAI Cloud", openai_key, "https://api.openai.com/v1", "gpt-4o-mini")
    else:
        print("\n--- OpenAI Cloud ---")
        print("⚠️ Skipped: No valid 'sk-' API key found in .env")

    # 2. Test Local LLM (as seen in logs)
    # The log showed: http://192.168.81.3:11434/v1
    local_url = "http://192.168.81.3:11434/v1"
    local_model = "openai/gpt-oss-20b"  # deduced from logs

    test_connection("Local LLM (Inferred from logs)", "local-dummy-key", local_url, local_model)


if __name__ == "__main__":
    main()
