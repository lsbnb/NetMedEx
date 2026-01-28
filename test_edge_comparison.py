#!/usr/bin/env python3
"""
Detailed comparison script: BioREx vs Semantic Analysis edges
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from netmedex.graph import PubTatorGraphBuilder
from netmedex.pubtator_parser import PubTatorIO


def compare_edges():
    """Compare BioREx and Semantic Analysis edges in detail"""
    
    print("=" * 80)
    print("Detailed Edge Comparison: BioREx vs Semantic Analysis")
    print("=" * 80)
    
    # Load test data
    test_file = "tests/test_data/22429397_abstract_240916.pubtator"
    collection = PubTatorIO.parse(test_file)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n❌ OPENAI_API_KEY not set")
        return
    
    # Build BioREx graph
    print("\n📊 Building BioREx Relations graph...")
    builder_biorex = PubTatorGraphBuilder(
        node_type="all",
        edge_method="relation"
    )
    builder_biorex.add_collection(collection)
    graph_biorex = builder_biorex.build(
        edge_weight_cutoff=0,
        community=False,
        max_edges=0
    )
    
    # Build Semantic graph
    print("📊 Building Semantic Analysis graph...")
    from openai import OpenAI
    
    class SimpleLLMClient:
        def __init__(self):
            self.client = OpenAI(api_key=api_key)
            self.model = "gpt-3.5-turbo"
    
    llm_client = SimpleLLMClient()
    
    builder_semantic = PubTatorGraphBuilder(
        node_type="all",
        edge_method="semantic",
        llm_client=llm_client,
        semantic_threshold=0.5
    )
    builder_semantic.add_collection(collection)
    graph_semantic = builder_semantic.build(
        edge_weight_cutoff=0,
        community=False,
        max_edges=0
    )
    
    # Extract BioREx edges
    print("\n" + "=" * 80)
    print("BioREx Edges (Expert Annotations)")
    print("=" * 80)
    
    biorex_edges = {}
    for i, (u, v, data) in enumerate(graph_biorex.edges(data=True), 1):
        u_name = graph_biorex.nodes[u].get('name', u)
        v_name = graph_biorex.nodes[v].get('name', v)
        relations = data.get('relations', {})
        rel_types = set()
        for pmid_rels in relations.values():
            rel_types.update(pmid_rels)
        
        edge_key = tuple(sorted([u, v]))
        biorex_edges[edge_key] = {
            'name': f"{u_name} ↔ {v_name}",
            'relations': rel_types
        }
        
        print(f"{i:2d}. {u_name} ↔ {v_name}")
        print(f"    Relation: {', '.join(rel_types)}")
    
    # Extract Semantic edges
    print("\n" + "=" * 80)
    print("Semantic Analysis Edges")
    print("=" * 80)
    
    semantic_edges = {}
    for i, (u, v, data) in enumerate(graph_semantic.edges(data=True), 1):
        u_name = graph_semantic.nodes[u].get('name', u)
        v_name = graph_semantic.nodes[v].get('name', v)
        relations = data.get('relations', {})
        rel_types = set()
        for pmid_rels in relations.values():
            rel_types.update(pmid_rels)
        
        edge_key = tuple(sorted([u, v]))
        semantic_edges[edge_key] = {
            'name': f"{u_name} ↔ {v_name}",
            'relations': rel_types
        }
        
        print(f"{i:2d}. {u_name} ↔ {v_name}")
        print(f"    Relation: {', '.join(rel_types)}")
    
    # Compare
    print("\n" + "=" * 80)
    print("Comparison Analysis")
    print("=" * 80)
    
    # Check which BioREx edges are in Semantic
    found_in_semantic = []
    not_found_in_semantic = []
    
    for edge_key, edge_info in biorex_edges.items():
        if edge_key in semantic_edges:
            found_in_semantic.append((edge_key, edge_info, semantic_edges[edge_key]))
        else:
            not_found_in_semantic.append((edge_key, edge_info))
    
    print(f"\n✅ BioREx edges FOUND in Semantic Analysis: {len(found_in_semantic)}/{len(biorex_edges)}")
    for edge_key, biorex_info, semantic_info in found_in_semantic:
        print(f"   • {biorex_info['name']}")
        print(f"     BioREx:   {', '.join(biorex_info['relations'])}")
        print(f"     Semantic: {', '.join(semantic_info['relations'])}")
    
    if not_found_in_semantic:
        print(f"\n❌ BioREx edges NOT FOUND in Semantic Analysis: {len(not_found_in_semantic)}/{len(biorex_edges)}")
        for edge_key, biorex_info in not_found_in_semantic:
            print(f"   • {biorex_info['name']}")
            print(f"     Relation: {', '.join(biorex_info['relations'])}")
    
    # Check Semantic edges not in BioREx (additional discoveries)
    additional_semantic = []
    for edge_key, edge_info in semantic_edges.items():
        if edge_key not in biorex_edges:
            additional_semantic.append((edge_key, edge_info))
    
    if additional_semantic:
        print(f"\n🔍 Additional edges found by Semantic Analysis: {len(additional_semantic)}")
        print("   (Not in BioREx - potentially new discoveries)")
        for edge_key, semantic_info in additional_semantic:
            print(f"   • {semantic_info['name']}")
            print(f"     Relation: {', '.join(semantic_info['relations'])}")
    
    # Summary statistics
    print("\n" + "=" * 80)
    print("Summary Statistics")
    print("=" * 80)
    
    recall = len(found_in_semantic) / len(biorex_edges) * 100 if biorex_edges else 0
    
    print(f"\nBioREx Edges: {len(biorex_edges)}")
    print(f"Semantic Edges: {len(semantic_edges)}")
    print(f"\nRecall (BioREx edges found): {len(found_in_semantic)}/{len(biorex_edges)} ({recall:.1f}%)")
    print(f"Additional discoveries: {len(additional_semantic)}")
    
    if recall >= 80:
        print(f"\n✅ EXCELLENT: Semantic analysis captured {recall:.1f}% of expert annotations!")
    elif recall >= 60:
        print(f"\n✓ GOOD: Semantic analysis captured {recall:.1f}% of expert annotations")
    else:
        print(f"\n⚠️  MODERATE: Semantic analysis captured {recall:.1f}% of expert annotations")


if __name__ == "__main__":
    compare_edges()
