from __future__ import annotations

import requests
import gradio as gr


def _api(base_url: str, method: str, path: str, payload: dict | None = None) -> dict:
    response = requests.request(
        method=method,
        url=f"{base_url.rstrip('/')}{path}",
        json=payload,
        timeout=300,
    )
    data = {}
    try:
        data = response.json()
    except Exception:
        data = {"detail": response.text}
    if not response.ok:
        raise RuntimeError(data.get("detail", f"HTTP {response.status_code}"))
    return data


def create_session(
    base_url: str,
    provider: str,
    model: str,
    edge_method: str,
    max_articles: int,
    sort: str,
    genes_csv: str,
    disease: str,
    query: str,
):
    payload = {
        "config": {
            "provider": provider,
            "model": model.strip() or None,
            "edge_method": edge_method,
            "max_articles": int(max_articles),
            "sort": sort,
        }
    }
    if query.strip():
        payload["query"] = query.strip()
    else:
        genes = [g.strip() for g in genes_csv.split(",") if g.strip()]
        payload["genes"] = genes
        payload["disease"] = disease.strip() or "osteoporosis"

    try:
        data = _api(base_url, "POST", "/sessions", payload)
        session_id = data["session_id"]
        context = data.get("context", {})
        status = (
            f"Session created: {session_id}\n"
            f"PMIDs: {context.get('pmid_count', '-')}, Query: {context.get('query', '-')}"
        )
        return session_id, status, []
    except Exception as e:
        return None, f"Create session failed: {e}", []


def ask(base_url: str, session_id: str | None, question: str, history: list[dict]):
    if not session_id:
        return history, "Please create session first."
    if not question.strip():
        return history, "Question is empty."

    next_history = history + [{"role": "user", "content": question}]
    try:
        data = _api(base_url, "POST", f"/sessions/{session_id}/ask", {"question": question})
        answer = data.get("message", "")
        if data.get("sources"):
            answer = f"{answer}\n\nSources: {', '.join(data['sources'])}"
        next_history.append({"role": "assistant", "content": answer})
        return next_history, "Ready."
    except Exception as e:
        next_history.append({"role": "assistant", "content": f"Error: {e}"})
        return next_history, f"Ask failed: {e}"


def close_session(base_url: str, session_id: str | None, history: list[dict]):
    if not session_id:
        return None, "No active session.", history
    try:
        _api(base_url, "DELETE", f"/sessions/{session_id}")
        return None, f"Session closed: {session_id}", history
    except Exception as e:
        return session_id, f"Close failed: {e}", history


with gr.Blocks(title="NetMedEx Gradio Chat") as demo:
    gr.Markdown("## NetMedEx Gradio Chat (via FastAPI Bridge)")
    session_id_state = gr.State(value=None)

    with gr.Row():
        base_url = gr.Textbox(label="API Base URL", value="http://127.0.0.1:8000")
        provider = gr.Dropdown(["openai", "google", "local"], value="google", label="Provider")
        model = gr.Textbox(label="Model", value="gemini-2.0-flash")
        edge_method = gr.Dropdown(["semantic", "co-occurrence", "relation"], value="semantic", label="Edge Method")

    with gr.Row():
        max_articles = gr.Number(label="Max Articles", value=120, precision=0)
        sort = gr.Dropdown(["score", "date"], value="score", label="Sort")
        disease = gr.Textbox(label="Disease", value="osteoporosis")

    genes_csv = gr.Textbox(label="Genes CSV", value="SOST,LRP5,TNFRSF11B,RUNX2,ALPL")
    query = gr.Textbox(label="Query (optional, overrides genes/disease)", value="")

    with gr.Row():
        create_btn = gr.Button("Create Session")
        close_btn = gr.Button("Close Session")
    status = gr.Textbox(label="Status", value="No session yet.", lines=3)

    chat = gr.Chatbot(type="messages", label="Chat")
    question = gr.Textbox(label="Question")
    ask_btn = gr.Button("Send")

    create_btn.click(
        create_session,
        inputs=[base_url, provider, model, edge_method, max_articles, sort, genes_csv, disease, query],
        outputs=[session_id_state, status, chat],
    )
    ask_btn.click(
        ask,
        inputs=[base_url, session_id_state, question, chat],
        outputs=[chat, status],
    )
    close_btn.click(
        close_session,
        inputs=[base_url, session_id_state, chat],
        outputs=[session_id_state, status, chat],
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
