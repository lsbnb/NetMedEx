#!/usr/bin/env python3
"""
Test script for semantic relationship extraction
Compares co-occurrence vs semantic analysis edge construction methods
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from netmedex.graph import PubTatorGraphBuilder
from netmedex.pubtator_parser import PubTatorIO


def test_semantic_analysis():
    """Test semantic analysis with real PubTator data"""
    
    print("=" * 80)
    print("Testing Semantic Relationship Extraction")
    print("=" * 80)
    
    # Load test data
    test_file = "tests/test_data/22429397_abstract_240916.pubtator"
    
    if not os.path.exists(test_file):
        print(f"Error: Test file not found: {test_file}")
        return
    
    print(f"\n📄 Loading data from: {test_file}")
    collection = PubTatorIO.parse(test_file)
    print(f"   Found {len(collection.articles)} article(s)")
    
    # Show article info
    for article in collection.articles:
        print(f"\n📝 Article PMID: {article.pmid}")
        print(f"   Title: {article.title}")
        print(f"   Annotations: {len(article.annotations)}")
        print(f"   Relations: {len(article.relations)}")
    
    # Check for LLM client
    print("\n" + "=" * 80)
    print("Checking LLM Configuration")
    print("=" * 80)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not set")
        print("\nTo test semantic analysis, set your API key:")
        print("   export OPENAI_API_KEY='sk-...'")
        print("\nContinuing with co-occurrence test only...")
        test_semantic = False
    else:
        print(f"✅ OPENAI_API_KEY found: {api_key[:10]}...")
        test_semantic = True
    
    # Test 1: Co-occurrence (baseline)
    print("\n" + "=" * 80)
    print("Test 1: Co-occurrence Edge Construction (Baseline)")
    print("=" * 80)
    
    builder_cooccur = PubTatorGraphBuilder(
        node_type="all",
        edge_method="co-occurrence"
    )
    builder_cooccur.add_collection(collection)
    graph_cooccur = builder_cooccur.build(
        edge_weight_cutoff=0,
        community=False,
        max_edges=0
    )
    
    print(f"\n📊 Co-occurrence Results:")
    print(f"   Nodes: {graph_cooccur.number_of_nodes()}")
    print(f"   Edges: {graph_cooccur.number_of_edges()}")
    
    # Show some edges
    if graph_cooccur.number_of_edges() > 0:
        print(f"\n   Sample edges (first 5):")
        for i, (u, v, data) in enumerate(graph_cooccur.edges(data=True)):
            if i >= 5:
                break
            u_name = graph_cooccur.nodes[u].get('name', u)
            v_name = graph_cooccur.nodes[v].get('name', v)
            print(f"   {i+1}. {u_name} ↔ {v_name}")
            print(f"      Relations: {list(data.get('relations', {}).values())}")
    
    # Test 2: Semantic Analysis
    if test_semantic:
        print("\n" + "=" * 80)
        print("Test 2: Semantic Analysis Edge Construction")
        print("=" * 80)
        
        try:
            from openai import OpenAI
            
            # Create simple LLM client
            class SimpleLLMClient:
                def __init__(self):
                    self.client = OpenAI(api_key=api_key)
                    self.model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
            
            llm_client = SimpleLLMClient()
            print(f"🤖 LLM Client initialized (model: {llm_client.model})")
            
            builder_semantic = PubTatorGraphBuilder(
                node_type="all",
                edge_method="semantic",
                llm_client=llm_client,
                semantic_threshold=0.5
            )
            
            print(f"\n⏳ Analyzing relationships with LLM...")
            print(f"   (This may take 1-2 seconds per article)")
            
            builder_semantic.add_collection(collection)
            graph_semantic = builder_semantic.build(
                edge_weight_cutoff=0,
                community=False,
                max_edges=0
            )
            
            print(f"\n📊 Semantic Analysis Results:")
            print(f"   Nodes: {graph_semantic.number_of_nodes()}")
            print(f"   Edges: {graph_semantic.number_of_edges()}")
            
            # Show edges with details
            if graph_semantic.number_of_edges() > 0:
                print(f"\n   Sample edges (first 5):")
                for i, (u, v, data) in enumerate(graph_semantic.edges(data=True)):
                    if i >= 5:
                        break
                    u_name = graph_semantic.nodes[u].get('name', u)
                    v_name = graph_semantic.nodes[v].get('name', v)
                    relations = data.get('relations', {})
                    print(f"   {i+1}. {u_name} ↔ {v_name}")
                    # Show relation types
                    rel_types = set()
                    for pmid_relations in relations.values():
                        rel_types.update(pmid_relations)
                    print(f"      Relation types: {rel_types}")
            
            # Comparison
            print("\n" + "=" * 80)
            print("Comparison: Co-occurrence vs Semantic Analysis")
            print("=" * 80)
            
            print(f"\nEdge Count:")
            print(f"   Co-occurrence:     {graph_cooccur.number_of_edges()}")
            print(f"   Semantic Analysis: {graph_semantic.number_of_edges()}")
            
            reduction = graph_cooccur.number_of_edges() - graph_semantic.number_of_edges()
            if graph_cooccur.number_of_edges() > 0:
                reduction_pct = (reduction / graph_cooccur.number_of_edges()) * 100
                print(f"   Reduction:         {reduction} edges ({reduction_pct:.1f}%)")
            
            print(f"\n💡 Interpretation:")
            if graph_semantic.number_of_edges() < graph_cooccur.number_of_edges():
                print(f"   ✅ Semantic analysis filtered out {reduction} edges")
                print(f"      This suggests improved precision by removing spurious co-occurrences")
            elif graph_semantic.number_of_edges() == graph_cooccur.number_of_edges():
                print(f"   ⚠️  Same number of edges - all co-occurrences appear meaningful")
            else:
                print(f"   ❓ More edges in semantic analysis - unexpected result")
            
            # Check cache stats
            if builder_semantic.semantic_extractor:
                cache_stats = builder_semantic.semantic_extractor.get_cache_stats()
                print(f"\n📦 Cache Statistics:")
                print(f"   Cached articles: {cache_stats['cached_articles']}")
                print(f"   Total edges:     {cache_stats['total_edges']}")
            
        except ImportError as e:
            print(f"\n❌ Error: Missing dependencies for semantic analysis")
            print(f"   {e}")
            print(f"\n   Install with: pip install openai python-dotenv")
        except Exception as e:
            print(f"\n❌ Error during semantic analysis:")
            print(f"   {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
    
    # Test 3: BioREx Relations Only
    print("\n" + "=" * 80)
    print("Test 3: BioREx Relations Only")
    print("=" * 80)
    
    builder_relation = PubTatorGraphBuilder(
        node_type="all",
        edge_method="relation"
    )
    builder_relation.add_collection(collection)
    graph_relation = builder_relation.build(
        edge_weight_cutoff=0,
        community=False,
        max_edges=0
    )
    
    print(f"\n📊 BioREx Relations Results:")
    print(f"   Nodes: {graph_relation.number_of_nodes()}")
    print(f"   Edges: {graph_relation.number_of_edges()}")
    
    if graph_relation.number_of_edges() > 0:
        print(f"\n   Expert-curated relationships:")
        for i, (u, v, data) in enumerate(graph_relation.edges(data=True)):
            u_name = graph_relation.nodes[u].get('name', u)
            v_name = graph_relation.nodes[v].get('name', v)
            relations = data.get('relations', {})
            rel_types = set()
            for pmid_relations in relations.values():
                rel_types.update(pmid_relations)
            print(f"   {i+1}. {u_name} ↔ {v_name}")
            print(f"      Relation types: {rel_types}")
    else:
        print("   No BioREx relations found in this dataset")
    
    print("\n" + "=" * 80)
    print("Test Complete!")
    print("=" * 80)


if __name__ == "__main__":
    test_semantic_analysis()
