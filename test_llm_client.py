"""
Unit tests for NetMedEx LLM integration.

This test file validates the LLM client functionality without requiring
a full NetMedEx installation or real OpenAI API calls.
"""

import sys
import os
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path to import webapp modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_imports():
    """Test that required modules can be imported."""
    try:
        from webapp.llm import LLMClient, llm_client
        print("✓ Successfully imported LLM modules")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_llm_client_initialization_without_key():
    """Test LLMClient initialization without API key."""
    from webapp.llm import LLMClient
    
    with patch.dict(os.environ, {}, clear=True):
        client = LLMClient()
        assert client.client is None, "Client should be None without API key"
        assert client.api_key is None, "API key should be None"
        print("✓ LLMClient correctly handles missing API key")
        return True


def test_llm_client_initialization_with_key():
    """Test LLMClient initialization with API key."""
    from webapp.llm import LLMClient
    
    test_key = "sk-test123456789"
    with patch.dict(os.environ, {"OPENAI_API_KEY": test_key}):
        with patch('webapp.llm.OpenAI') as mock_openai:
            mock_openai.return_value = MagicMock()
            client = LLMClient()
            assert client.api_key == test_key, f"API key should be {test_key}"
            assert client.client is not None, "Client should be initialized"
            mock_openai.assert_called_once()
            print("✓ LLMClient correctly initializes with API key")
            return True


def test_query_translation_with_mock():
    """Test natural language to boolean query translation with mocked OpenAI."""
    from webapp.llm import LLMClient
    
    # Create client with mocked OpenAI
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        with patch('webapp.llm.OpenAI') as mock_openai:
            # Setup mock response
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = '"Lung Neoplasms" AND @GENE'
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            client = LLMClient()
            
            # Test query translation
            natural_query = "genes related to lung cancer"
            result = client.translate_query_to_boolean(natural_query)
            
            assert result == '"Lung Neoplasms" AND @GENE', f"Expected boolean query, got: {result}"
            print(f"✓ Query translation works: '{natural_query}' → '{result}'")
            return True


def test_query_translation_fallback_without_client():
    """Test that query translation falls back to original query without client."""
    from webapp.llm import LLMClient
    
    with patch.dict(os.environ, {}, clear=True):
        client = LLMClient()
        natural_query = "genes related to lung cancer"
        result = client.translate_query_to_boolean(natural_query)
        
        assert result == natural_query, "Should return original query as fallback"
        print("✓ Query translation correctly falls back without API key")
        return True


def test_abstract_summarization_with_mock():
    """Test abstract summarization with mocked OpenAI."""
    from webapp.llm import LLMClient
    
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}):
        with patch('webapp.llm.OpenAI') as mock_openai:
            # Setup mock response
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Summary: The selected abstracts discuss gene-disease relationships."
            mock_client.chat.completions.create.return_value = mock_response
            mock_openai.return_value = mock_client
            
            client = LLMClient()
            
            # Test summarization
            test_abstracts = [
                "Title: Gene A in Disease B\nAbstract: This study shows...",
                "Title: Gene C affects Disease D\nAbstract: We investigated..."
            ]
            result = client.summarize_abstracts(test_abstracts)
            
            assert "Summary" in result, f"Expected summary in result, got: {result}"
            print(f"✓ Abstract summarization works: {result[:50]}...")
            return True


def test_abstract_summarization_without_client():
    """Test abstract summarization error handling without client."""
    from webapp.llm import LLMClient
    
    with patch.dict(os.environ, {}, clear=True):
        client = LLMClient()
        test_abstracts = ["Abstract 1", "Abstract 2"]
        result = client.summarize_abstracts(test_abstracts)
        
        assert "Error" in result or "not configured" in result, "Should return error message"
        print("✓ Abstract summarization correctly handles missing client")
        return True


def test_api_key_update():
    """Test updating API key after initialization."""
    from webapp.llm import LLMClient
    
    with patch.dict(os.environ, {}, clear=True):
        with patch('webapp.llm.OpenAI') as mock_openai:
            mock_openai.return_value = MagicMock()
            
            client = LLMClient()
            assert client.client is None, "Client should start as None"
            
            # Update API key
            client.update_api_key("sk-newkey123")
            assert client.api_key == "sk-newkey123", "API key should be updated"
            mock_openai.assert_called_once()
            print("✓ API key update functionality works")
            return True


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "="*60)
    print("NetMedEx LLM Integration - Unit Tests")
    print("="*60 + "\n")
    
    tests = [
        ("Module Import", test_imports),
        ("Client Init (No Key)", test_llm_client_initialization_without_key),
        ("Client Init (With Key)", test_llm_client_initialization_with_key),
        ("Query Translation (Mocked)", test_query_translation_with_mock),
        ("Query Translation (Fallback)", test_query_translation_fallback_without_client),
        ("Abstract Summarization (Mocked)", test_abstract_summarization_with_mock),
        ("Abstract Summarization (No Client)", test_abstract_summarization_without_client),
        ("API Key Update", test_api_key_update),
    ]
    
    passed = 0
    failed = 0
    errors = []
    
    for test_name, test_func in tests:
        print(f"\nTest: {test_name}")
        print("-" * 60)
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                errors.append(f"{test_name}: Test returned False")
        except Exception as e:
            failed += 1
            errors.append(f"{test_name}: {str(e)}")
            print(f"✗ Test failed with error: {e}")
    
    print("\n" + "="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60)
    
    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")
    
    return passed, failed


if __name__ == "__main__":
    passed, failed = run_all_tests()
    sys.exit(0 if failed == 0 else 1)
