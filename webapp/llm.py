from __future__ import annotations

import logging
import os

import requests
from openai import OpenAI

logger = logging.getLogger(__name__)

OPENAI_BASE_URL = "https://api.openai.com/v1"
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

COMMON_OPENAI_MODELS = {
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
    "o1",
    "o1-mini",
    "o1-preview",
    "o3",
    "o3-mini",
    "o4-mini",
}


def normalize_model_for_provider(provider: str | None, model: str | None) -> str:
    """
    Normalize provider/model combinations to avoid common misconfiguration errors.
    - OpenAI provider should use bare model IDs (e.g. gpt-4o-mini, not openai/gpt-4o-mini)
    - OpenRouter provider usually expects namespaced IDs; auto-prefix common OpenAI IDs
    """
    raw_provider = (provider or "openai").strip().lower()
    raw_model = (model or "").strip()
    if not raw_model:
        if raw_provider == "openrouter":
            return "openai/gpt-4o-mini"
        if raw_provider == "google":
            return "gemini-1.5-pro"
        return "gpt-4o-mini"

    if raw_provider == "openai":
        if "/" in raw_model:
            # Fix common OpenRouter-style model notation under OpenAI provider.
            return raw_model.rsplit("/", 1)[-1].strip() or "gpt-4o-mini"
        return raw_model

    if raw_provider == "openrouter":
        if "/" not in raw_model and raw_model in COMMON_OPENAI_MODELS:
            return f"openai/{raw_model}"
        return raw_model

    return raw_model


class LLMClient:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai")
        self.api_key = None
        self.base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.safety_setting = os.getenv("GOOGLE_SAFETY_SETTING", "medium")
        self.client = None

        # Provider-specific env resolution (with legacy fallbacks).
        if self.provider == "google":
            self.api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            self.base_url = self.base_url or GEMINI_OPENAI_BASE_URL
            self.model = os.getenv("GOOGLE_MODEL", self.model)
            self.embedding_model = os.getenv("GOOGLE_EMBEDDING_MODEL", self.embedding_model)
        elif self.provider == "openrouter":
            self.api_key = os.getenv("OPENROUTER_API_KEY")
            self.base_url = self.base_url or OPENROUTER_BASE_URL
            self.model = os.getenv("OPENROUTER_MODEL", self.model)
        elif self.provider == "local":
            self.api_key = os.getenv("LOCAL_LLM_API_KEY") or "local-dummy-key"
            self.base_url = (
                self.base_url or os.getenv("LOCAL_LLM_BASE_URL") or "http://localhost:11434/v1"
            )
            self.model = os.getenv("LOCAL_LLM_MODEL", self.model)
            self.embedding_model = os.getenv("LOCAL_EMBEDDING_MODEL", self.embedding_model)
        else:
            self.api_key = os.getenv("OPENAI_API_KEY")
            self.base_url = self.base_url or OPENAI_BASE_URL
        self.model = normalize_model_for_provider(self.provider, self.model)

        # Initialize client if key/base_url configuration is usable.
        if self.provider == "local":
            if self.base_url:
                self.initialize_client()
                logger.info(
                    f"Local LLM Client auto-initialized from environment: {self.base_url} with model: {self.model}"
                )
            else:
                logger.info("LLM Client not auto-initialized: local base URL missing")
        elif self.api_key:
            self.initialize_client()
            logger.info(
                f"LLM Client auto-initialized from environment with provider: {self.provider}, model: {self.model}, embedding: {self.embedding_model}"
            )
        else:
            logger.info("LLM Client not auto-initialized: No valid API key in environment")

    def initialize_client(
        self,
        api_key=None,
        base_url=None,
        model=None,
        embedding_model=None,
        provider=None,
        safety_setting=None,
    ):
        if api_key:
            self.api_key = api_key
        if base_url:
            self.base_url = base_url
        if model:
            self.model = model
        if embedding_model:
            self.embedding_model = embedding_model
        if provider:
            self.provider = provider
        if safety_setting:
            self.safety_setting = safety_setting
        self.model = normalize_model_for_provider(self.provider, self.model)

        if self.api_key:
            # OpenRouter headers (optional but recommended for rate limiting/diagnostics)
            extra_headers = {}
            if self.provider == "openrouter":
                extra_headers = {
                    "HTTP-Referer": "https://github.com/NetMedEx/NetMedEx",
                    "X-Title": "NetMedEx",
                }
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                default_headers=extra_headers,
            )
            logger.info(
                f"LLM Client initialized with provider: {self.provider}, model: {self.model}, embedding: {self.embedding_model}"
            )
        else:
            logger.warning("LLM Client not initialized: No API Key provided")

    def test_connection(self) -> tuple[bool, str]:
        if not self.client:
            return False, "Client not initialized"
        try:
            models_list = self.client.models.list()
            available_models = [m.id for m in models_list.data]

            # Check primary model
            if self.provider == "google":
                # Gemini model IDs can include suffixes like "-latest".
                has_google_model = any(self.model in m for m in available_models)
                if not has_google_model:
                    return False, f"Model '{self.model}' not found on Gemini endpoint."
            elif self.model not in available_models:
                return False, f"Model '{self.model}' not found on server. Please pull it first."

            return True, "Connection successful"
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False, str(e)

    def update_api_key(self, api_key):
        self.api_key = api_key
        self.initialize_client()

    def chat_completion_text(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 200,
        timeout: float = 180.0,
        response_format: dict | None = None,
    ) -> str:
        """
        Unified chat completion helper.
        - All providers (OpenAI, Google/Gemini, and local LLMs) now use the OpenAI SDK
          via the initialized client for consistency and correct URL/header handling.
        """
        if not self.api_key:
            raise ValueError("LLM API key is not configured")

        if not self.client:
            raise ValueError("LLM client not initialized")

        # Use max_completion_tokens and fixed temperature for newer/restricted models
        limit_param = "max_tokens"
        actual_temp = temperature

        model_lower = str(self.model).lower()
        # Reasoning models (o1, o3) typically have fixed/restricted sampling parameters.
        # gpt-4o, gpt-4o-mini, and most others support standard temperature (0-2).
        is_reasoning_model = any(m in model_lower for m in ["o1", "o3"])
        is_mini_nano = any(m in model_lower for m in ["nano", "mini"])

        if is_reasoning_model:
            limit_param = "max_completion_tokens"
            actual_temp = 1.0
        elif is_mini_nano or "gpt-4o" in model_lower:
            # Note: Some OpenRouter/Local providers might not support max_completion_tokens
            # We prefer max_tokens for OpenRouter/Local for better compatibility.
            if self.provider in ["openrouter", "local"]:
                limit_param = "max_tokens"
            else:
                limit_param = "max_completion_tokens"
            # Support lower temperature for these models
            actual_temp = temperature

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": actual_temp,
            "timeout": timeout,
        }
        kwargs[limit_param] = max_tokens

        if response_format:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if content is None:
            return ""
        return str(content).strip()

    def translate_to_english(self, text: str) -> str:
        """
        Translates text to English unconditionally.
        Keeps original formatting / text if already in English or translation fails.
        """
        if not self.client:
            return text

        system_prompt = (
            "You are a professional all-around expert in biomedical literature, specializing in finding information and precise translation. "
            "Your task is to translate and restructure the user's query into precise English for scientific search. "
            "If the query is already in English, return it exactly as is. "
            "Optimize the terminology for biomedical databases (e.g., use 'Neoplasms' or 'Cancer' appropriately). "
            "Do NOT add any explanations, boolean operators (AND/OR), or quotes unless they were in the original. "
            "Just return the translated and restructured English text."
        )

        try:
            translated = self.chat_completion_text(
                messages=[
                    {
                        "role": "user",
                        "content": f"{system_prompt}\n\nTask: Translate the following text to English.\nText: {text}",
                    },
                ],
                temperature=0.1,
                max_tokens=200,
            )
            return translated
        except Exception as e:
            logger.error(f"LLM Error during query translation to English: {e}")
            return text

    def translate_query_to_boolean(self, natural_query: str) -> str:
        """
        Translates a natural language query into a PubTator3 boolean query key.
        """
        if not self.client:
            return natural_query  # Fallback if no client

        system_prompt = (
            "You are a professional all-around expert in biomedical literature, specializing in finding information and optimizing search queries. "
            "Your task is to translate, restructure, and optimize natural language queries into optimized boolean queries for PubTator3. "
            "PubTator3 supports entity types like @GENE, @DISEASE, @CHEMICAL, @SPECIES, etc., but also standard text search. "
            "Use standard boolean operators: AND, OR, NOT. Use quotes for exact phrases. "
            "IMPORTANT: If the user's query is in a language other than English (e.g., Traditional Chinese, Japanese, Korean), "
            "you MUST first translate and restructure the concepts into scientifically accurate English before building the boolean query. "
            "If the user's query is very broad (e.g., just 'Cancer', 'Gene', 'Protein'), you MUST add specific constraints "
            "to prevent API timeout errors (HTTP 502). "
            "CRITICAL: Do NOT use specific field tags like [Title/Abstract], [Title], [Author], etc. "
            "These tags often cause internal server errors (HTTP 500) in the PubTator3 API. "
            "Just use keywords, entity tags, and boolean operators. "
            "Examples: "
            "'骨質疏鬆的基因' -> '\"Osteoporosis\" AND @GENE' "
            "'Lung cancer genes' -> '\"Lung Neoplasms\" AND @GENE' "
            "'胃癌與幽門螺旋桿菌的關係' -> '\"Stomach Neoplasms\" AND \"Helicobacter pylori\"' "
            '\'covid 19 treatment with aspirin\' -> \'"COVID-19" AND "Aspirin" AND "Therapeutics"\' '
            "Return ONLY the English boolean query string. Do not include explanations, quotes around the result, or markdown blocks."
        )

        def _clean_boolean_query(text: str) -> str:
            import re

            boolean_query = text or ""
            code_match = re.search(r"```(?:[a-zA-Z]*)?\s*([\s\S]*?)\s*```", boolean_query)
            if code_match:
                boolean_query = code_match.group(1).strip()

            boolean_query = re.sub(
                r"^(Query|Boolean|Result|Output):\s*", "", boolean_query, flags=re.IGNORECASE
            )
            boolean_query = (
                boolean_query.replace("**", "").replace("__", "").replace("`", "").strip()
            )
            boolean_query = re.sub(r"\s+", " ", boolean_query).strip()

            # If it looks like a sentence, try to extract a quoted boolean candidate.
            if len(boolean_query.split()) > 10 and '"' in boolean_query:
                quoted = re.findall(r'"([^"]*)"', boolean_query)
                for q in quoted:
                    if any(op in q.upper() for op in ("AND", "OR", "NOT", "@")):
                        boolean_query = q
                        break

            # Strip one pair of outer quotes only when the whole output is quoted.
            if (
                boolean_query.startswith('"')
                and boolean_query.endswith('"')
                and boolean_query.count('"') == 2
            ):
                boolean_query = boolean_query[1:-1]
            return boolean_query.strip()

        def _is_valid_boolean_query(text: str) -> bool:
            import re

            if not text or not isinstance(text, str):
                return False
            q = text.strip()
            if not q:
                return False
            if q.count('"') % 2 != 0:
                return False
            if re.search(r"\b(SELECT|FROM|WHERE|LIMIT|ORDER BY)\b", q, re.IGNORECASE):
                return False
            # Reject clearly non-PubTator wrappers often emitted by local models.
            if "[" in q or "]" in q:
                return False
            if re.search(r"(AND|OR|NOT)\s*$", q, re.IGNORECASE):
                return False
            if re.search(r"[@]\s*$", q):
                return False
            if q.endswith("("):
                return False
            if not re.search(r"[A-Za-z0-9]", q):
                return False
            return True

        def _fallback_boolean_query(query: str) -> str:
            q = (query or "").strip()
            if not q:
                return natural_query

            import re

            terms: list[str] = []

            # 1. Look for known entities of interest
            if re.search(r"\b(mirna|micro ?rna)\b", q, re.IGNORECASE):
                terms.append('"miRNA"')
            if re.search(r"\bosteoporosis\b", q, re.IGNORECASE):
                terms.append('"Osteoporosis"')

            # Add more specific entity search if needed
            if len(terms) < 2:
                # Basic scientific term extraction (3+ chars, skipping common words)
                keywords = re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", q)
                for kw in keywords:
                    up = kw.lower()
                    if up in {
                        "the",
                        "and",
                        "among",
                        "with",
                        "for",
                        "about",
                        "relationship",
                        "of",
                        "genes",
                        "related",
                        "to",
                    }:
                        continue
                    candidate = f'"{kw}"'
                    if candidate not in terms:
                        terms.append(candidate)
                    if len(terms) >= 2:
                        break

            # 2. If we found solid terms, use them
            if terms and len(terms) >= 2:
                return " AND ".join(terms[:2])

            # 3. Fallback: if the original query already contains boolean operators or entity tags, trust it
            upper_q = q.upper()
            if (
                any(op in upper_q for op in (" AND ", " OR ", " NOT "))
                or "@GENE" in upper_q
                or "@MIRNA" in upper_q
                or "@DISEASE" in upper_q
                or "@CHEMICAL" in upper_q
            ):
                return q

            if terms:
                return " AND ".join(terms[:2])
            return natural_query

        try:
            logger.debug("Translating natural language query to boolean syntax.")
            raw_query = self.chat_completion_text(
                messages=[
                    {
                        "role": "user",
                        "content": f"{system_prompt}\n\nTask: Translate the following natural language query into a PubTator3 boolean query.\nQuery: {natural_query}",
                    },
                ],
                temperature=0.1,
                max_tokens=200,
            )
            logger.debug("Received boolean query candidate from provider.")

            boolean_query = _clean_boolean_query(raw_query)

            # Recovery pass for providers that often emit truncated/empty outputs.
            if not _is_valid_boolean_query(boolean_query):
                strict_prompt = (
                    "You are converting one biomedical query to PubTator boolean syntax.\n"
                    "Output exactly ONE COMPLETE line.\n"
                    "Use only quoted terms, AND/OR/NOT, and optional @GENE/@DISEASE/@CHEMICAL/@SPECIES.\n"
                    "No explanation, no markdown, no labels.\n"
                    "The query must be syntactically complete (no trailing operator or quote)."
                )
                retry_raw = self.chat_completion_text(
                    messages=[
                        {"role": "system", "content": strict_prompt},
                        {"role": "user", "content": f"Query: {natural_query}"},
                    ],
                    temperature=0.0,
                    max_tokens=80,
                )
                logger.info(f"Strict retry boolean query response: '{retry_raw}'")
                boolean_query = _clean_boolean_query(retry_raw)

            if not _is_valid_boolean_query(boolean_query):
                fallback = _fallback_boolean_query(natural_query)
                logger.warning(
                    f"Boolean query invalid after retry. Using fallback. original='{natural_query}' fallback='{fallback}'"
                )
                boolean_query = fallback

            logger.info(f"Final cleaned boolean query: '{boolean_query}'")

            return boolean_query
        except Exception as e:
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
            return self.chat_completion_text(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful biomedical research assistant.",
                    },
                    {"role": "user", "content": f"{user_prompt}\n\nAbstracts:\n{combined_text}"},
                ],
                temperature=0.3,
                max_tokens=800,
            )
        except Exception as e:
            logger.error(f"LLM Error during summarization: {e}")
            return f"Error during analysis: {str(e)}"

    def get_openai_models(self, api_key: str) -> list[str]:
        """
        Fetch available models from OpenAI API using the provided key.
        """
        if not api_key:
            return []

        try:
            # Create a temporary client for this request
            temp_client = OpenAI(api_key=api_key, base_url=OPENAI_BASE_URL)
            models_page = temp_client.models.list()

            # Extract model IDs
            model_ids = [m.id for m in models_page.data]

            # Keep chat/reasoning model families and filter out non-chat model families.
            chat_prefixes = ("gpt", "chatgpt", "o1", "o3", "o4")
            excluded_keywords = (
                "embedding",
                "whisper",
                "tts",
                "realtime",
                "moderation",
                "transcribe",
                "search",
                "image",
                "audio",
                "omni-moderation",
            )
            chat_models = []
            for model_id in model_ids:
                model_lower = model_id.lower()
                if not model_lower.startswith(chat_prefixes):
                    continue
                # Local model tags like "gpt-oss:20b" should never appear in OpenAI model dropdown.
                if ":" in model_lower:
                    continue
                if "instruct" in model_lower:
                    continue
                if any(keyword in model_lower for keyword in excluded_keywords):
                    continue
                chat_models.append(model_id)

            # Sort: Prioritize current recommendations
            priority_models = [
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-4.1",
                "gpt-4.1-mini",
                "o4-mini",
                "o3-mini",
                "gpt-4-turbo",
                "o1-mini",
                "gpt-3.5-turbo",
            ]
            sorted_models = []

            for pm in priority_models:
                if pm in chat_models:
                    sorted_models.append(pm)
                    chat_models.remove(pm)

            # Append rest sorted alphabetically
            sorted_models.extend(sorted(chat_models))

            return sorted_models

        except Exception as e:
            logger.error(f"Error fetching OpenAI models: {e}")
            raise e

    def get_gemini_models(self, api_key: str) -> list[str]:
        """
        Fetch available Gemini generative models from Google AI API.
        Returns normalized model IDs like 'gemini-1.5-pro'.
        """
        if not api_key:
            return []

        try:
            if not api_key.startswith("AIza"):
                raise ValueError(
                    "Invalid Gemini API key format. Use an API key from Google AI Studio (starts with 'AIza')."
                )
            url = "https://generativelanguage.googleapis.com/v1beta/models"
            response = requests.get(url, params={"key": api_key}, timeout=8)
            if response.status_code == 401:
                raise ValueError(
                    "Gemini authentication failed (401). Check API key validity and API restrictions."
                )
            response.raise_for_status()
            data = response.json()
            raw_models = data.get("models", [])

            model_ids = []
            for model in raw_models:
                name = model.get("name", "")  # e.g., "models/gemini-1.5-pro-latest"
                if not name.startswith("models/"):
                    continue
                normalized = name.split("/", 1)[1]
                if not normalized.startswith("gemini"):
                    continue
                if "embedding" in normalized:
                    continue
                model_ids.append(normalized)

            # Deduplicate and sort with useful defaults first.
            model_ids = sorted(set(model_ids))
            preferred = [
                "gemini-1.5-pro",
                "gemini-1.5-flash",
                "gemini-2.0-flash",
            ]
            sorted_models = []
            for p in preferred:
                for mid in model_ids:
                    if mid == p or mid.startswith(f"{p}-"):
                        if mid not in sorted_models:
                            sorted_models.append(mid)
            for mid in model_ids:
                if mid not in sorted_models:
                    sorted_models.append(mid)

            return sorted_models
        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else "unknown"
            logger.error(f"Error fetching Gemini models: HTTP {status_code}")
            raise ValueError(f"Gemini models API error (HTTP {status_code}).") from e
        except Exception as e:
            logger.error(f"Error fetching Gemini models: {e}")
            raise e

    def get_openrouter_models(self, api_key: str) -> list[str]:
        """
        Fetch available models from OpenRouter API using the provided key.
        OpenRouter also uses the OpenAI-compatible models.list() endpoint.
        """
        if not api_key:
            return []

        try:
            temp_client = OpenAI(api_key=api_key, base_url=OPENROUTER_BASE_URL)
            models_page = temp_client.models.list()
            model_ids = [m.id for m in models_page.data]

            # OpenRouter has 1000s of models. Let's provide some sensible sorting.
            # We'll prioritize common/recommended ones and keep the rest.
            priority_prefixes = (
                "openai/",
                "anthropic/",
                "google/",
                "meta-llama/",
                "mistralai/",
                "deepseek/",
            )

            filtered_models = []
            for mid in model_ids:
                if any(mid.startswith(p) for p in priority_prefixes):
                    filtered_models.append(mid)
                elif "/" not in mid:  # Catch-all for simple names
                    filtered_models.append(mid)

            # Sort: Priority ones first
            recommended = [
                "openai/gpt-4o-mini",
                "openai/gpt-4o",
                "anthropic/claude-3.5-sonnet",
                "deepseek/deepseek-chat",
                "google/gemini-2.0-flash-001",
                "meta-llama/llama-3.1-405b-instruct",
            ]

            sorted_models = []
            for r in recommended:
                if r in filtered_models:
                    sorted_models.append(r)
                    filtered_models.remove(r)

            sorted_models.extend(sorted(filtered_models))
            return sorted_models

        except Exception as e:
            logger.error(f"Error fetching OpenRouter models: {e}")
            raise e


# Singleton instance
llm_client = LLMClient()
