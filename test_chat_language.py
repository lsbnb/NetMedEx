"""
Direct language-matching test for Chat Panel system prompt.
Calls OpenAI directly with the exact system prompt used in production.
"""

from dotenv import load_dotenv

load_dotenv()

from webapp.llm import llm_client
from netmedex.chat import ChatSession
from netmedex.rag import AbstractRAG, AbstractDocument

DUMMY_GRAPH_CONTEXT = """
Graph Structure:
- Node: Icariin [Chemical]
- Node: Osteoblast [Cell Line]
- Edge: Icariin ↔ Osteoblast [PMID:12345678, activate]
"""

DUMMY_ABS_TEXT = """PMID: 12345678
Title: Effect of Icariin on osteoblast differentiation
Abstract: Icariin promotes osteoblast differentiation and bone formation through activation of Wnt signaling. This compound derived from Epimedium herb upregulates miR-21 which inhibits PTEN."""

QUERIES = [
    ("English", "What is the role of Icariin in osteoblast differentiation?"),
    ("Japanese", "イカリイン（Icariin）は骨芽細胞の分化にどのような役割を果たしていますか？"),
    ("Chinese", "淫羊藿苷（Icariin）在骨芽細胞分化中扮演什麼角色？"),
]


def main():
    print("=" * 60)
    print("Chat Language Matching Test")
    print("=" * 60)

    if not llm_client.client:
        print("ERROR: LLM client not configured. Check .env for OPENAI_API_KEY.")
        return

    # Use the exact system prompt from production (ChatSession)
    # Instantiate a minimal ChatSession to borrow the system_prompt
    rag = AbstractRAG(llm_client)
    rag.documents = {
        "12345678": AbstractDocument(
            pmid="12345678",
            title="Effect of Icariin on osteoblast differentiation",
            abstract="Icariin promotes osteoblast differentiation and bone formation through activation of Wnt signaling. Upregulates miR-21 which inhibits PTEN.",
            entities=[{"text": "Icariin", "type": "Chemical"}],
            edges=[],
        )
    }
    session = ChatSession(rag_system=rag, llm_client=llm_client)
    system_prompt = session.system_prompt

    for lang, query in QUERIES:
        print(f"\n[{lang}] Query:\n  {query}")
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Context:\n{DUMMY_GRAPH_CONTEXT}\n\n"
                    f"Abstracts:\n{DUMMY_ABS_TEXT}\n\n"
                    f"Question: {query}"
                ),
            },
        ]
        resp = llm_client.client.chat.completions.create(
            model=llm_client.model,
            messages=messages,
            temperature=0.3,
        )
        answer = resp.choices[0].message.content
        print(f"\n  Response (first 500 chars):\n  {answer[:500]}")
        print("-" * 60)


if __name__ == "__main__":
    main()
