import os
import json
import time
import logging
from dataclasses import asdict
from dotenv import load_dotenv
from typing import Any

# NetMedEx imports
from webapp.llm import LLMClient
from netmedex.semantic_re import SemanticRelationshipExtractor
from netmedex.pubtator_data import PubTatorArticle, PubTatorAnnotation, PubTatorCollection
from netmedex.pubtator_graph_data import PubTatorNode

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("benchmark")

def run_benchmark(query_text: str, pmid_list: list[str]):
    load_dotenv()
    
    # We will use simplified mock data for benchmarking since we can't easily hit PubTator here
    # without a full app context, OR we can try to fetch real data if needed.
    # For now, let's assume we have a few articles to test.
    
    # 1. Mock articles for consistent comparison
    articles = [
        PubTatorArticle(
            pmid="33454230",
            title="Lutein and Zeaxanthin in Eye Health",
            abstract="Lutein and zeaxanthin are xanthophyll carotenoids that accumulate in the retina. They are known to protect against age-related macular degeneration (AMD) by filtering blue light and acting as antioxidants. Studies show that lutein intake significantly increases macular pigment optical density and decreases the risk of cataract progression. Lutein also interacts with glutathione to maintain redox balance.",
            date="2021",
            journal="Nutrients",
            doi=None,
            annotations=[
                PubTatorAnnotation("33454230", 0, 6, "Lutein", "Lutein", "Chemical", "D007333"),
                PubTatorAnnotation("33454230", 4, 14, "Zeaxanthin", "Zeaxanthin", "Chemical", "D015033"),
                PubTatorAnnotation("33454230", 94, 100, "Retina", "Retina", "Species", "D012160"),
                PubTatorAnnotation("33454230", 143, 177, "Macular Degeneration", "Macular Degeneration", "Disease", "D008268"),
                PubTatorAnnotation("33454230", 280, 288, "Cataract", "Cataract", "Disease", "D002386"),
                PubTatorAnnotation("33454230", 314, 325, "Glutathione", "Glutathione", "Chemical", "D005978"),
            ],
            relations=[]
        ),
        PubTatorArticle(
            pmid="30123456",
            title="Metformin and Alzheimer's Disease",
            abstract="Metformin, a common type 2 diabetes drug, has been studied for its effects on cognitive function. Some research suggests metformin activates AMPK, which in turn inhibits mTOR signaling in neurons. This mechanism is thought to reduce amyloid-beta plaque formation and potentially treat Alzheimer's disease. However, high doses may cause vitamin B12 deficiency which associates with neuropathy.",
            date="2018",
            journal="JAD",
            doi=None,
            annotations=[
                PubTatorAnnotation("30123456", 0, 9, "Metformin", "Metformin", "Chemical", "D008687"),
                PubTatorAnnotation("30123456", 11, 26, "Type 2 Diabetes", "Type 2 Diabetes", "Disease", "D003924"),
                PubTatorAnnotation("30123456", 87, 91, "AMPK", "AMPK", "Gene", "5562"),
                PubTatorAnnotation("30123456", 103, 107, "mTOR", "mTOR", "Gene", "2475"),
                PubTatorAnnotation("30123456", 141, 153, "Amyloid-beta", "Amyloid-beta", "Chemical", "D016229"),
                PubTatorAnnotation("30123456", 192, 211, "Alzheimer's disease", "Alzheimer's disease", "Disease", "D000544"),
                PubTatorAnnotation("30123456", 240, 251, "Vitamin B12", "Vitamin B12", "Chemical", "D014805"),
            ],
            relations=[]
        )
    ]

    nodes_map = {}
    for art in articles:
        nodes_map[art.pmid] = {}
        for ann in art.annotations:
            node_id = ann.get_mesh_node_id()[0]
            nodes_map[art.pmid][node_id] = PubTatorNode(
                mesh=ann.mesh, type=ann.type, name=ann.name, pmid=art.pmid
            )

    results = []

    # Get Gemini key from .env (currently stored as OPENAI_API_KEY in this specific .env setup)
    gemini_key = os.getenv("OPENAI_API_KEY")
    if not gemini_key or not gemini_key.startswith("AIza"):
        print("⚠️ Warning: Could not find valid Gemini API key (AIza...) in .env")

    # Providers to test
    configs = [
        {"name": "Google (Gemini 1.5 Flash)", "provider": "google", "model": "gemini-flash-latest", "key": gemini_key},
        {"name": "Google (Gemini 1.5 Pro)", "provider": "google", "model": "gemini-pro-latest", "key": gemini_key}
    ]

    # Check if a real OpenAI key is provided via env (not the AIza one)
    real_openai_key = os.getenv("REAL_OPENAI_API_KEY") # Or we can ask user
    if real_openai_key:
        configs.insert(0, {"name": "OpenAI (GPT-4o-mini)", "provider": "openai", "model": "gpt-4o-mini", "key": real_openai_key})

    for config in configs:
        if not config['key']:
            print(f"Skipping {config['name']} due to missing API key.")
            continue
            
        print(f"\n>>> Benchmarking: {config['name']} ...")
        
        # Initialize client
        client = LLMClient()
        if config['provider'] == 'openai':
            client.initialize_client(
                api_key=config['key'], 
                provider=config['provider'], 
                model=config['model'],
                base_url="https://api.openai.com/v1"
            )
        else:
            client.initialize_client(
                api_key=config['key'], 
                provider=config['provider'], 
                model=config['model'],
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )

        extractor = SemanticRelationshipExtractor(client, confidence_threshold=0.3)
        
        start_time = time.time()
        all_edges = []
        pmid_data = {}
        
        for art in articles:
            pmid_start = time.time()
            try:
                edges = extractor.analyze_article_relationships(art, nodes_map[art.pmid])
                pmid_elapsed = time.time() - pmid_start
                all_edges.extend(edges)
                pmid_data[art.pmid] = {
                    "edges_count": len(edges),
                    "time": pmid_elapsed
                }
                print(f"  PMID {art.pmid}: Found {len(edges)} edges in {pmid_elapsed:.2f}s")
            except Exception as e:
                print(f"  PMID {art.pmid}: Error - {e}")
                pmid_data[art.pmid] = {"edges_count": 0, "time": 0}

        total_elapsed = time.time() - start_time
        avg_speed = total_elapsed / len(articles) if articles else 0

        results.append({
            "config": config['name'],
            "total_edges": len(all_edges),
            "total_time": total_elapsed,
            "avg_speed": avg_speed,
            "pmids": pmid_data
        })

    # Generate Markdown Table
    if results:
        print("\n\n### LLM Recall & Speed Benchmark Result")
        pmid_headers = " | ".join([f"PMID {p} Edges" for p in pmid_data.keys()])
        separator = " | ".join([":---:" for _ in pmid_data.keys()])
        print(f"| Provider | Total Edges | Total Time (s) | Avg Sec/Article | {pmid_headers} |")
        print(f"| :--- | :---: | :---: | :---: | {separator} |")
        for res in results:
            pmid_vals = " | ".join([str(res['pmids'][p]['edges_count']) for p in pmid_data.keys()])
            print(f"| {res['config']} | {res['total_edges']} | {res['total_time']:.2f} | {res['avg_speed']:.2f} | {pmid_vals} |")
    else:
        print("\nNo results collected. Please provide API keys.")

if __name__ == "__main__":
    run_benchmark("", [])
