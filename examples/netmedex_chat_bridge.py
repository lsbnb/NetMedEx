from __future__ import annotations

from netmedex.chat_bridge import BridgeConfig, NetMedExChatBridge


if __name__ == "__main__":
    cfg = BridgeConfig(
        provider="google",
        model="gemini-2.0-flash",
        max_articles=120,
        edge_method="semantic",
    )
    bridge = NetMedExChatBridge(cfg)

    genes = ["SOST", "LRP5", "TNFRSF11B", "RUNX2", "ALPL"]
    context = bridge.build_context_from_genes(genes=genes, disease="osteoporosis")
    print(f"Context ready: {context}")

    response = bridge.ask("Summarize the strongest evidence linking these genes to osteoporosis.")
    if response.get("success"):
        print(response.get("message", ""))
        if response.get("sources"):
            print(f"Sources: {', '.join(response['sources'])}")
    else:
        print(f"Error: {response.get('error', 'Unknown error')}")
