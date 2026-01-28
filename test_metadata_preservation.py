#!/usr/bin/env python3
"""
Test script to verify confidence and evidence are preserved in graph edges
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from netmedex.graph import PubTatorGraphBuilder
from netmedex.pubtator_parser import PubTatorIO


def test_metadata_preservation():
    """Test that semantic metadata is preserved in graph edges"""
    
    print("=" * 80)
    print("Testing Semantic Metadata Preservation")
    print("=" * 80)
    
    # Load test data
    test_file = "tests/test_data/22429397_abstract_240916.pubtator"
    collection = PubTatorIO.parse(test_file)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n❌ OPENAI_API_KEY not set")
        print("This test requires an API key to generate semantic edges")
        return
    
    print(f"\n📄 Loading data from: {test_file}")
    print(f"   Articles: {len(collection.articles)}")
    
    # Build graph with semantic analysis
    from openai import OpenAI
    
    class SimpleLLMClient:
        def __init__(self):
            self.client = OpenAI(api_key=api_key)
            self.model = "gpt-3.5-turbo"
    
    llm_client = SimpleLLMClient()
    
    print("\n🤖 Building graph with semantic analysis...")
    builder = PubTatorGraphBuilder(
        node_type="all",
        edge_method="semantic",
        llm_client=llm_client,
        semantic_threshold=0.5
    )
    
    builder.add_collection(collection)
    graph = builder.build(
        edge_weight_cutoff=0,
        community=False,
        max_edges=0
    )
    
    print(f"\n📊 Graph built:")
    print(f"   Nodes: {graph.number_of_nodes()}")
    print(f"   Edges: {graph.number_of_edges()}")
    
    # Check for metadata in edges
    print("\n" + "=" * 80)
    print("Checking Edge Metadata")
    print("=" * 80)
    
    edges_with_confidence = 0
    edges_with_evidence = 0
    edges_without_metadata = 0
    
    for u, v, data in graph.edges(data=True):
        has_conf = data.get("confidences") is not None
        has_evid = data.get("evidences") is not None
        
        if has_conf:
            edges_with_confidence += 1
        if has_evid:
            edges_with_evidence += 1
        if not has_conf and not has_evid:
            edges_without_metadata += 1
    
    print(f"\n📊 Metadata Statistics:")
    print(f"   Edges with confidence scores: {edges_with_confidence}/{graph.number_of_edges()}")
    print(f"   Edges with evidence text:     {edges_with_evidence}/{graph.number_of_edges()}")
    print(f"   Edges without metadata:       {edges_without_metadata}/{graph.number_of_edges()}")
    
    # Show detailed examples
    print("\n" + "=" * 80)
    print("Example Edges with Metadata (first 5)")
    print("=" * 80)
    
    count = 0
    for u, v, data in graph.edges(data=True):
        if count >= 5:
            break
        
        confidences = data.get("confidences", {})
        evidences = data.get("evidences", {})
        
        u_name = graph.nodes[u].get('name', u)
        v_name = graph.nodes[v].get('name', v)
        
        print(f"\n{count + 1}. {u_name} ↔ {v_name}")
        print(f"   Relations: {data.get('relations', {})}")
        
        if confidences:
            print(f"   ✅ Confidences:")
            for pmid, rel_confs in confidences.items():
                for rel_type, conf in rel_confs.items():
                    print(f"      PMID {pmid}, {rel_type}: {conf:.3f}")
        else:
            print(f"   ❌ No confidence data")
        
        if evidences:
            print(f"   ✅ Evidence:")
            for pmid, rel_evids in evidences.items():
                for rel_type, evid in rel_evids.items():
                    # Truncate long evidence
                    evid_short = evid[:100] + "..." if len(evid) > 100 else evid
                    print(f"      PMID {pmid}, {rel_type}:")
                    print(f"         \"{evid_short}\"")
        else:
            print(f"   ❌ No evidence data")
        
        count += 1
    
    # Validation
    print("\n" + "=" * 80)
    print("Validation Results")
    print("=" * 80)
    
    if edges_with_confidence == graph.number_of_edges():
        print("\n✅ SUCCESS: All edges have confidence scores!")
    elif edges_with_confidence > 0:
        print(f"\n⚠️  PARTIAL: {edges_with_confidence}/{graph.number_of_edges()} edges have confidence scores")
    else:
        print("\n❌ FAILURE: No edges have confidence scores")
    
    if edges_with_evidence == graph.number_of_edges():
        print("✅ SUCCESS: All edges have evidence text!")
    elif edges_with_evidence > 0:
        print(f"⚠️  PARTIAL: {edges_with_evidence}/{graph.number_of_edges()} edges have evidence text")
    else:
        print("❌ FAILURE: No edges have evidence text")
    
    # Test accessing metadata programmatically
    print("\n" + "=" * 80)
    print("Programmatic Access Example")
    print("=" * 80)
    
    for u, v, data in list(graph.edges(data=True))[:1]:  # Just first edge
        print(f"\nAccessing metadata for edge: {u} ↔ {v}")
        print(f"\nMethod 1: Direct dictionary access")
        print(f"  confidences = graph.edges['{u}', '{v}']['confidences']")
        print(f"  evidences = graph.edges['{u}', '{v}']['evidences']")
        
        confidences = data.get('confidences', {})
        evidences = data.get('evidences', {})
        
        print(f"\nMethod 2: From edge data")
        print(f"  confidences = {confidences}")
        print(f"  evidences = {evidences}")


if __name__ == "__main__":
    test_metadata_preservation()
