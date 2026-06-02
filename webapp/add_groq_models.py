with open("webapp/llm.py") as f:
    content = f.read()

# Add get_groq_models method to LLMClient class
method = """
    def get_groq_models(self, api_key: str) -> list[str]:
        import requests
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json().get("data", [])
                return [m.get("id") for m in data if m.get("id")]
            return []
        except Exception as e:
            logger.error(f"Failed to fetch Groq models: {e}")
            return []
"""

# Insert before get_openrouter_models
content = content.replace(
    "    def get_openrouter_models", method + "\n    def get_openrouter_models"
)

with open("webapp/llm.py", "w") as f:
    f.write(content)
