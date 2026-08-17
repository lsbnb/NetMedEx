from evaluation.run_hybrid_gain_ablation import ARMS


def test_next_generation_ablation_has_requested_isolated_arms():
    assert tuple(ARMS) == ("B", "C1", "C2", "D1", "D2", "D3", "Oracle")
    assert "--disable-kg-reranking" in ARMS["C2"]["flags"]
    assert "all_safe" in ARMS["D1"]["flags"]
    assert "incremental" in ARMS["D2"]["flags"]
    assert "natural" in ARMS["D3"]["flags"]
    assert "local_oracle" in ARMS["Oracle"]["flags"]
