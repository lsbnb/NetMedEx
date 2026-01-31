#!/usr/bin/env python
"""
Interactive test script for NetMedEx LLM features.

This script allows manual testing of the LLM client with OpenAI API or local LLM.
Usage: python test_llm_interactive.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def setup_llm_client():
    """Setup LLM client with user's choice of provider."""
    from webapp.llm import llm_client

    print("\n" + "=" * 70)
    print(" NetMedEx LLM Integration - Interactive Testing")
    print("=" * 70)
    print("\nChoose your LLM provider:")
    print("  1. OpenAI API (requires API key)")
    print("  2. Local LLM (http://localhost:11434/api/chat)")
    print("  3. Skip testing")

    choice = input("\nYour choice (1/2/3): ").strip()

    if choice == "1":
        # OpenAI API
        api_key = input("Enter your OpenAI API key: ").strip()
        if not api_key:
            print("❌ No API key provided. Exiting.")
            return None
        llm_client.initialize_client(api_key=api_key)
        print(f"✓ Initialized with OpenAI (model: {llm_client.model})")
        return llm_client

    elif choice == "2":
        # Local LLM
        print("\n🔧 Setting up local LLM...")
        # For local LLM, we need a dummy API key and the custom base URL
        local_url = "http://localhost:11434/v1"  # OpenAI-compatible endpoint
        model = input("Enter model name (or press Enter for 'llama2'): ").strip() or "llama2"

        llm_client.initialize_client(
            api_key="local-llm-key",  # Dummy key for local LLM
            base_url=local_url,
            model=model,
        )
        print(f"✓ Initialized with local LLM at {local_url} (model: {model})")
        return llm_client

    else:
        print("Skipping LLM testing.")
        return None


def test_query_translation_interactive(client):
    """Interactive test for query translation."""
    if not client or not client.client:
        print("\n❌ LLM client not initialized.")
        return False

    print("\n" + "=" * 60)
    print("Test: Natural Language Query Translation")
    print("=" * 60)

    test_queries = [
        "genes related to lung cancer",
        "covid 19 treatment with aspirin",
        "BRCA1 mutations in breast cancer patients",
        "diabetes and cardiovascular disease risk factors",
    ]

    print("\nTesting with sample queries:")
    for query in test_queries:
        print(f"\nNatural Language: {query}")
        try:
            boolean_query = client.translate_query_to_boolean(query)
            print(f"Boolean Query:    {boolean_query}")
            print("✓ Success")
        except Exception as e:
            print(f"✗ Error: {e}")
            return False

    # Interactive mode
    print("\n" + "-" * 60)
    print("Interactive Mode - Enter your own queries (or 'quit' to exit)")
    print("-" * 60)

    while True:
        user_query = input("\nYour query: ").strip()
        if user_query.lower() in ["quit", "exit", "q", ""]:
            break

        try:
            boolean_query = client.translate_query_to_boolean(user_query)
            print(f"→ Boolean: {boolean_query}")
        except Exception as e:
            print(f"✗ Error: {e}")

    return True


def test_summarization_interactive(client):
    """Interactive test for abstract summarization."""
    if not client or not client.client:
        print("\n❌ LLM client not initialized.")
        return False

    print("\n" + "=" * 60)
    print("Test: Abstract Summarization")
    print("=" * 60)

    sample_abstracts = [
        """Title: BRCA1 mutations and breast cancer risk
Abstract: This study examines the relationship between BRCA1 gene mutations and breast cancer susceptibility. We analyzed 500 patients and found that BRCA1 mutations significantly increase breast cancer risk by 70%. The findings suggest early screening is crucial for carriers.""",
        """Title: BRCA2 in hereditary breast cancer
Abstract: BRCA2 mutations account for approximately 20% of hereditary breast cancer cases. Our research demonstrates that BRCA2 carriers have a lifetime risk of developing breast cancer of up to 85%. Preventive strategies should be considered.""",
        """Title: Genetic counseling for BRCA carriers
Abstract: Genetic counseling plays a vital role in managing BRCA mutation carriers. This review discusses risk assessment, prevention options, and psychological support for individuals with BRCA mutations.""",
    ]

    print("\nSummarizing sample abstracts about BRCA and breast cancer...")
    print("-" * 60)

    try:
        summary = client.summarize_abstracts(sample_abstracts)
        print("\n📄 Generated Summary:")
        print(summary)
        print("\n✓ Summarization successful")
        return True
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run interactive tests."""
    # Setup LLM client
    client = setup_llm_client()
    if not client:
        print("\n⚠️  No LLM client configured. Exiting.")
        return

    print("\n" + "=" * 70)
    print("Starting LLM Feature Tests")
    print("=" * 70)
    print("\n⚠️  Note: This will make actual API calls and may consume credits.\n")

    # Test query translation
    print("\n[Test 1/2] Natural Language Query Translation")
    if not test_query_translation_interactive(client):
        print("\n⚠️  Query translation test failed.")
        return

    # Test summarization
    proceed = input("\n\nProceed to test abstract summarization? (y/n): ").strip().lower()
    if proceed == "y":
        print("\n[Test 2/2] Abstract Summarization")
        test_summarization_interactive(client)

    print("\n" + "=" * 70)
    print("✅ Interactive testing completed!")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Test the web application with: netmedex run")
    print("  2. Or use Docker: docker run -p 8050:8050 lsbnb/netmedex")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Testing interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
