from unittest.mock import AsyncMock, patch
from netmedex.pubtator import PubTatorAPI

def test_dynamic_fetch_loop():
    # We will test PubTatorAPI in query mode with max_articles = 3.
    # The search query will return 6 PMIDs: ["1", "2", "3", "4", "5", "6"]
    # Batch 1 (initial_size = min(6, 3*1.1+2) = 5 PMIDs: ["1", "2", "3", "4", "5"])
    # We mock responses so that PMIDs 2, 4, and 5 are skipped (missing passages).
    # Batch 1 will yield only 2 valid articles (PMIDs 1 and 3).
    # Since we need 3, we must fetch the next batch (PMID 6).
    # Batch 2 yields 1 valid article (PMID 6).
    # Total valid articles at the end: 3 (PMIDs 1, 3, 6).
    
    api = PubTatorAPI(query="test_query", max_articles=3)
    
    mock_get_query_results = AsyncMock(return_value=["1", "2", "3", "4", "5", "6"])
    
    response_batch1 = {
        "PubTator3": [
            {
                "pmid": "1",
                "passages": [
                    {"infons": {"section_type": "TITLE", "type": "title"}, "text": "Title 1", "annotations": []},
                    {"infons": {"section_type": "ABSTRACT", "type": "abstract"}, "text": "Abstract 1", "annotations": []},
                ],
                "relations": [],
            },
            {
                "pmid": "2",
                "passages": [],  # Skipped!
                "relations": [],
            },
            {
                "pmid": "3",
                "passages": [
                    {"infons": {"section_type": "TITLE", "type": "title"}, "text": "Title 3", "annotations": []},
                    {"infons": {"section_type": "ABSTRACT", "type": "abstract"}, "text": "Abstract 3", "annotations": []},
                ],
                "relations": [],
            },
            {
                "pmid": "4",
                "passages": [],  # Skipped!
                "relations": [],
            },
            {
                "pmid": "5",
                "passages": [],  # Skipped!
                "relations": [],
            },
        ]
    }
    
    response_batch2 = {
        "PubTator3": [
            {
                "pmid": "6",
                "passages": [
                    {"infons": {"section_type": "TITLE", "type": "title"}, "text": "Title 6", "annotations": []},
                    {"infons": {"section_type": "ABSTRACT", "type": "abstract"}, "text": "Abstract 6", "annotations": []},
                ],
                "relations": [],
            }
        ]
    }
    
    mock_batch_search = AsyncMock()
    mock_batch_search.side_effect = [[response_batch1], [response_batch2]]
    
    with patch.object(api, "get_query_results", mock_get_query_results), \
         patch.object(api, "batch_publication_search", mock_batch_search):
        result = api.run()
        
        # Verify query search called
        mock_get_query_results.assert_called_once_with("test_query")
        
        # Verify batch_publication_search called twice with correct slices
        assert mock_batch_search.call_count == 2
        mock_batch_search.assert_any_call(["1", "2", "3", "4", "5"])
        mock_batch_search.assert_any_call(["6"])
        
        # Verify we got exactly 3 articles back
        assert len(result.articles) == 3
        pmids = [a.pmid for a in result.articles]
        assert pmids == ["1", "3", "6"]
