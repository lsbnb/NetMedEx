
import os
import logging
from openai import OpenAI, OpenAIError

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        self.client = None
        
        # Initialize client if API key is present
        self.initialize_client()

    def initialize_client(self, api_key=None, base_url=None, model=None):
        if api_key:
            self.api_key = api_key
        if base_url:
            self.base_url = base_url
        if model:
            self.model = model
            
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            logger.info(f"LLM Client initialized with model: {self.model}")
        else:
            logger.warning("LLM Client not initialized: No API Key provided")

    def update_api_key(self, api_key):
        self.api_key = api_key
        self.initialize_client()

    def translate_query_to_boolean(self, natural_query: str) -> str:
        """
        Translates a natural language query into a PubTator3 boolean query key.
        """
        if not self.client:
            return natural_query # Fallback if no client

        system_prompt = (
            "You are an expert in biomedical information retrieval. "
            "Your task is to translate natural language queries into optimized boolean queries for PubTator3. "
            "PubTator3 supports entity types like @GENE, @DISEASE, @CHEMICAL, @SPECIES, etc., but also standard text search. "
            "Use standard boolean operators: AND, OR, NOT. Use quotes for exact phrases. "
            "Examples: "
            "'Genes related to lung cancer' -> '\"Lung Neoplasms\" AND @GENE' "
            "'covid 19 treatment with aspirin' -> '\"COVID-19\" AND \"Aspirin\" AND \"Therapeutics\"' "
            "Return ONLY the boolean query string. Do not include explanations, quotes around the result, or markdown blocks."
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": natural_query}
                ],
                temperature=0,
                max_tokens=60
            )
            boolean_query = response.choices[0].message.content.strip()
            # Cleanup widely used markdown code blocks if any
            if boolean_query.startswith("```") and boolean_query.endswith("```"):
                boolean_query = boolean_query.strip("`")
                if boolean_query.startswith("markdown"):  boolean_query = boolean_query[8:]
                boolean_query = boolean_query.strip()
            
            return boolean_query
        except OpenAIError as e:
            logger.error(f"LLM Error during query translation: {e}")
            return natural_query

    def summarize_abstracts(self, abstracts: list[str], prompt_instruction: str = None) -> str:
        """
        Summarizes a list of abstracts based on a prompt.
        """
        if not self.client:
            return "Error: LLM Client is not configured. Please set your API Key in the settings."

        if not abstracts:
            return "No abstracts provided for analysis."

        # Combine abstracts (truncate if too long - naive truncation for now)
        # Assuming avg 3 chars per token, 4000 tokens ~ 12000 chars.
        # Let's target input of ~10k chars max for safety on smaller models.
        combined_text = "\n\n".join(abstracts)
        if len(combined_text) > 12000:
            combined_text = combined_text[:12000] + "\n...(truncated)..."

        default_prompt = (
            "The following are abstracts from scientific papers. "
            "Please analyze them and summarize the key findings, relationships, and biological mechanisms described. "
            "Focus on the entities involved in the network selection."
        )
        
        user_prompt = prompt_instruction if prompt_instruction else default_prompt

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful biomedical research assistant."},
                    {"role": "user", "content": f"{user_prompt}\n\nAbstracts:\n{combined_text}"}
                ],
                temperature=0.3,
                max_tokens=800
            )
            return response.choices[0].message.content.strip()
        except OpenAIError as e:
            logger.error(f"LLM Error during summarization: {e}")
            return f"Error during analysis: {str(e)}"

# Singleton instance
llm_client = LLMClient()
