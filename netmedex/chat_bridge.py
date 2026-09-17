from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from netmedex.chat import ChatSession
from netmedex.graph import PubTatorGraphBuilder
from netmedex.graph_rag import GraphRetriever
from netmedex.node_rag import GraphNode, NodeRAG
from netmedex.pubtator import PubTatorAPI
from netmedex.rag import AbstractDocument, AbstractRAG
from webapp.llm import LLMClient, get_provider_api_key


@dataclass
class BridgeConfig:
    provider: str = "openai"  # openai | google | local | anthropic | groq | nvidia | openrouter
    api_key: str | None = None
    model: str | None = None
    base_url: str | None = None
    max_articles: int = 200
    sort: str = "score"  # score | date
    full_text: bool = False
    edge_method: str = "semantic"  # co-occurrence | semantic | relation
    semantic_threshold: float = 0.5
    top_k: int = 5
    max_history: int = 10
    session_language: str = "English"
    # Optional separate model for Chat generation (Layer 1-5 synthesis), distinct
    # from the model above used for graph-building semantic edge extraction.
    # Extraction is called once per article and is a narrower task (classify the
    # relation between two given entities in one abstract); Chat synthesis is
    # called once per question and must read/reason across many abstracts at
    # once -- the two steps don't need the same model. Leave these unset to reuse
    # the graph-building client for Chat too (today's behavior, unchanged).
    chat_provider: str | None = None
    chat_api_key: str | None = None
    chat_model: str | None = None
    chat_base_url: str | None = None


class NetMedExChatBridge:
    """Bridge for embedding NetMedEx search->network->chat in another app."""

    def __init__(self, config: BridgeConfig):
        self.config = config
        self.llm_client = self._init_llm_client(config)
        self.chat_llm_client = self._init_chat_llm_client(config, self.llm_client)
        self.session: ChatSession | None = None
        self.graph = None
        self.last_query: str | None = None

    @staticmethod
    def build_gene_disease_query(genes: list[str], disease: str = "osteoporosis") -> str:
        normalized_genes = [g.strip() for g in genes if g and g.strip()]
        if not normalized_genes:
            raise ValueError("At least one non-empty gene symbol is required.")
        gene_clause = " OR ".join(f'"{gene}"' for gene in normalized_genes)
        return f'"{disease}" AND ({gene_clause})'

    def build_context_from_genes(
        self, genes: list[str], disease: str = "osteoporosis"
    ) -> dict[str, Any]:
        query = self.build_gene_disease_query(genes=genes, disease=disease)
        return self.build_context_from_query(query)

    def build_context_from_query(self, query: str) -> dict[str, Any]:
        api = PubTatorAPI(
            query=query,
            pmid_list=None,
            sort=self.config.sort,
            request_format="biocjson",
            max_articles=self.config.max_articles,
            full_text=self.config.full_text,
            queue=None,
        )
        collection = api.run()

        llm_for_graph = self.llm_client if self.config.edge_method == "semantic" else None
        graph_builder = PubTatorGraphBuilder(
            node_type="all",
            edge_method=self.config.edge_method,
            llm_client=llm_for_graph,
            semantic_threshold=self.config.semantic_threshold,
        )
        graph_builder.add_collection(collection)
        graph = graph_builder.build(
            pmid_weights=None,
            weighting_method="freq",
            edge_weight_cutoff=0,
            community=False,
            max_edges=0,
        )

        pmid_titles = {str(k): v for k, v in graph.graph.get("pmid_title", {}).items()}
        pmid_abstracts = {str(k): v for k, v in graph.graph.get("pmid_abstract", {}).items()}
        pmids = sorted(set(pmid_titles.keys()) | set(pmid_abstracts.keys()))
        if not pmids:
            raise RuntimeError("No PMID metadata found in graph.")

        pmid_edges = self._collect_pmid_edges(graph)
        documents = [
            AbstractDocument(
                pmid=pmid,
                title=pmid_titles.get(pmid, f"PMID {pmid}"),
                abstract=pmid_abstracts.get(pmid, "Abstract not available."),
                entities=[],
                edges=pmid_edges.get(pmid, []),
            )
            for pmid in pmids
        ]

        rag_system = AbstractRAG(self.llm_client)
        indexed_count = rag_system.index_abstracts(documents)

        node_rag = None
        try:
            node_rag = NodeRAG(self.llm_client)
            graph_nodes = [
                GraphNode(
                    node_id=str(node_id),
                    name=str(data.get("name", node_id)),
                    type=str(data.get("type", "Entity")),
                    metadata=data,
                )
                for node_id, data in graph.nodes(data=True)
            ]
            node_rag.index_nodes(graph_nodes)
        except Exception:
            node_rag = None

        graph_retriever = GraphRetriever(graph, node_rag=node_rag)
        self.session = ChatSession(
            rag_system,
            self.chat_llm_client,
            graph_retriever=graph_retriever,
            max_history=self.config.max_history,
            topic=self.last_query if self.last_query else "biomedical research",
        )
        self.graph = graph
        self.last_query = query
        return {
            "query": query,
            "indexed_abstracts": indexed_count,
            "pmid_count": len(pmids),
        }

    def ask(self, question: str) -> dict[str, Any]:
        if self.session is None:
            raise RuntimeError(
                "Context is not initialized. Call build_context_from_query(...) first."
            )
        return self.session.send_message(
            question,
            top_k=self.config.top_k,
            session_language=self.config.session_language,
        )

    @staticmethod
    def _collect_pmid_edges(graph) -> dict[str, list[dict[str, Any]]]:
        pmid_edges: dict[str, list[dict[str, Any]]] = {}
        for u, v, data in graph.edges(data=True):
            relations = data.get("relations", {})
            relation_pmids = relations.keys() if isinstance(relations, dict) else []
            fallback_pmids = data.get("pmids", [])
            if isinstance(fallback_pmids, str):
                fallback_pmids = [fallback_pmids]

            all_pmids = set(str(p) for p in relation_pmids) | set(str(p) for p in fallback_pmids)
            for pmid in all_pmids:
                pmid_edges.setdefault(pmid, []).append(
                    {
                        "source": str(u),
                        "target": str(v),
                        "relations": sorted(relations.get(pmid, []))
                        if isinstance(relations, dict)
                        else [],
                    }
                )
        return pmid_edges

    @staticmethod
    def _init_llm_client(config: BridgeConfig) -> LLMClient:
        llm_client = LLMClient()
        provider = config.provider
        # Must match SessionConfigModel.provider's allowed pattern in fastapi_bridge.py.
        if provider not in {"openai", "google", "local", "anthropic", "groq", "nvidia", "openrouter"}:
            raise ValueError(f"Unsupported provider: {provider}")

        api_key = get_provider_api_key(provider, config.api_key)
        base_url = config.base_url or (
            os.getenv("LOCAL_LLM_BASE_URL") if provider == "local" else None
        )

        if not api_key:
            raise ValueError(f"Missing API key for provider '{provider}'.")

        llm_client.initialize_client(
            api_key=api_key,
            base_url=base_url,
            model=config.model,
            provider=provider,
        )
        return llm_client

    @staticmethod
    def _init_chat_llm_client(config: BridgeConfig, build_llm_client: LLMClient) -> LLMClient:
        """Return the LLM client Chat generation should use.

        Reuses the graph-building client unless the caller explicitly configured
        a distinct chat_provider/chat_api_key/chat_model/chat_base_url -- so
        existing callers that never set these see no behavior change.
        """
        wants_override = any(
            [
                config.chat_provider,
                config.chat_api_key,
                config.chat_model,
                config.chat_base_url,
            ]
        )
        if not wants_override:
            return build_llm_client

        chat_config = BridgeConfig(
            provider=config.chat_provider or config.provider,
            api_key=config.chat_api_key,
            model=config.chat_model,
            base_url=config.chat_base_url,
        )
        return NetMedExChatBridge._init_llm_client(chat_config)
