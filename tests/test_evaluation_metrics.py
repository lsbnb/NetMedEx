import pytest

from evaluation.metrics import (
    _bootstrap_mean_ci,
    _bpref,
    _dcg,
    score_arm_exposures,
    _sign_test_p_value,
    cohens_kappa,
    fleiss_kappa,
    krippendorff_alpha,
    score_edge_ratings,
    score_edge_verification_delta,
    score_mean_ratings,
    score_path_qrels,
    score_retrieval,
)


def test_dcg_uses_exponential_graded_gain():
    assert _dcg([2, 1]) == pytest.approx(3 + 1 / 1.584962500721156)


def test_bpref_requires_judged_nonrelevant_documents():
    assert _bpref(["A"], {"A": 2, "B": 1}) is None
    assert _bpref(["A", "X", "C"], {"A": 2, "B": 1, "C": 0}) == 0.5


def test_retrieval_reports_judgment_coverage():
    qrels = [
        {"question_id": "Q001", "pmid": "A", "relevance": "2"},
        {"question_id": "Q001", "pmid": "B", "relevance": "1"},
        {"question_id": "Q001", "pmid": "C", "relevance": "0"},
    ]
    runs = [
        {
            "system": "netmedex",
            "question_id": "Q001",
            "rank": "1",
            "pmid": "A",
        },
        {
            "system": "netmedex",
            "question_id": "Q001",
            "rank": "2",
            "pmid": "X",
        },
        {
            "system": "netmedex",
            "question_id": "Q001",
            "rank": "3",
            "pmid": "C",
        },
    ]

    result = score_retrieval(qrels, runs)["netmedex"]

    assert result["precision_at_5"] == 0.2
    assert result["recall_at_10"] == 0.5
    assert result["judged_at_10"] == 0.6667
    assert result["unjudged_at_10"] == 0.3333
    assert result["returned_at_10"] == 0.3
    assert result["bpref"] == 0.5
    assert result["bpref_evaluable_questions"] == 1
    assert result["question_count"] == 1


def test_retrieval_reports_paired_question_level_comparison():
    qrels = [
        {"question_id": "Q001", "pmid": "A", "relevance": "2"},
        {"question_id": "Q002", "pmid": "B", "relevance": "2"},
    ]
    runs = [
        {"system": "hybrid", "question_id": "Q001", "rank": "1", "pmid": "A"},
        {"system": "text", "question_id": "Q001", "rank": "1", "pmid": "X"},
        {"system": "hybrid", "question_id": "Q002", "rank": "1", "pmid": "X"},
        {"system": "text", "question_id": "Q002", "rank": "1", "pmid": "B"},
    ]

    paired = score_retrieval(qrels, runs)["_paired_comparison"]

    assert paired["n_questions"] == 2
    assert paired["diff_direction"] == "hybrid minus text"
    assert paired["metrics"]["precision_at_5"]["mean_diff"] == 0.0
    assert paired["metrics"]["precision_at_5"]["wins_first_system"] == 1
    assert paired["metrics"]["precision_at_5"]["wins_second_system"] == 1


def test_cohens_kappa_perfect_agreement_is_one():
    assert cohens_kappa([0, 1, 0, 1, 1], [0, 1, 0, 1, 1]) == 1.0


def test_cohens_kappa_below_chance_agreement_is_negative():
    # Every judgment disagrees -- worse than chance, kappa must be negative.
    assert cohens_kappa([0, 0, 1, 1], [1, 1, 0, 0]) < 0


def test_cohens_kappa_undefined_when_no_variation():
    # Both raters always pick the same single category -- there's no variation to measure
    # agreement against chance, so kappa is undefined (None), not a misleading 1.0 or 0.0.
    assert cohens_kappa([1, 1, 1], [1, 1, 1]) is None


def test_multi_rater_agreement_is_one_for_perfect_variable_labels():
    ratings = [[0, 0, 0], [1, 1, 1], [0, 0, 0], [1, 1, 1]]
    assert fleiss_kappa(ratings) == 1.0
    assert krippendorff_alpha(ratings, level="nominal") == 1.0


def test_ordinal_alpha_penalizes_large_disagreements():
    close = [[3, 3, 4], [4, 4, 5], [1, 1, 2]]
    far = [[1, 1, 5], [5, 5, 1], [1, 1, 5]]
    assert krippendorff_alpha(close, level="ordinal") > krippendorff_alpha(
        far, level="ordinal"
    )


def test_cohens_kappa_quadratic_weight_penalizes_distant_disagreement_more():
    # Same number of disagreements, but the "far" case (1 vs 5) should score a lower (worse)
    # quadratic-weighted kappa than the "close" case (3 vs 4).
    close_disagreement = cohens_kappa([3, 3, 3, 3], [4, 4, 4, 4], weighted="quadratic")
    far_disagreement = cohens_kappa([1, 1, 1, 1], [5, 5, 5, 5], weighted="quadratic")
    assert close_disagreement is None or far_disagreement is None or far_disagreement <= close_disagreement


def test_bootstrap_mean_ci_on_constant_values_is_a_point():
    point, lo, hi = _bootstrap_mean_ci([0.5, 0.5, 0.5, 0.5], n_resamples=500)
    assert point == 0.5
    assert lo == pytest.approx(0.5, abs=1e-9)
    assert hi == pytest.approx(0.5, abs=1e-9)


def test_bootstrap_mean_ci_single_value_returns_none_bounds():
    point, lo, hi = _bootstrap_mean_ci([0.7])
    assert point == 0.7
    assert lo is None and hi is None


def test_bootstrap_mean_ci_is_reproducible_with_fixed_seed():
    values = [0.1, 0.3, -0.2, 0.4, 0.0, 0.25, -0.1]
    first = _bootstrap_mean_ci(values, n_resamples=2000)
    second = _bootstrap_mean_ci(values, n_resamples=2000)
    assert first == second


def test_sign_test_all_positive_is_significant():
    # n=6, all same sign: p = 2*C(6,0)/2**6 = 0.03125 -- the smallest attainable p-value at n=5
    # (0.0625) isn't below the conventional 0.05 threshold, so this uses n=6 to cross it.
    assert _sign_test_p_value([0.1, 0.2, 0.3, 0.15, 0.05, 0.25]) < 0.05


def test_sign_test_balanced_diffs_is_not_significant():
    assert _sign_test_p_value([0.1, -0.1, 0.2, -0.2]) == 1.0


def test_sign_test_ignores_exact_ties():
    # Ties (diff == 0) are excluded before the sign test, per the standard convention -- leaving
    # a perfectly balanced 1-1 split among the remaining non-zero diffs, i.e. p=1.0.
    assert _sign_test_p_value([0.0, 0.0, 0.1, -0.1]) == 1.0


def _edge_row(edge_id, rater_id, meaningful, relation_correct):
    return {
        "system": "netmedex_hybrid_rag",
        "edge_id": edge_id,
        "rater_id": rater_id,
        "biologically_meaningful": meaningful,
        "relation_type_correct": relation_correct,
    }


def _path_qrel_row(
    qid,
    path_id,
    source,
    bridge,
    target,
    rel1,
    rel2,
    dir1,
    dir2,
    pmids,
    relevance="2",
    negative="0",
):
    return {
        "question_id": qid,
        "path_id": path_id,
        "source": source,
        "bridge": bridge,
        "target": target,
        "relation_1": rel1,
        "relation_2": rel2,
        "direction_1": dir1,
        "direction_2": dir2,
        "pmids": pmids,
        "relevance": relevance,
        "is_negative_control": negative,
    }


def _path_run_row(system, qid, rank, source, bridge, target, rel1, rel2, dir1, dir2, pmids):
    return {
        "system": system,
        "question_id": qid,
        "path_rank": str(rank),
        "source": source,
        "bridge": bridge,
        "target": target,
        "relation_1": rel1,
        "relation_2": rel2,
        "direction_1": dir1,
        "direction_2": dir2,
        "pmids": pmids,
    }


def test_score_edge_ratings_reports_kappa_and_ci_with_two_raters():
    rows = [
        _edge_row("Q001-E01", "raterA", "1", "1"),
        _edge_row("Q001-E01", "raterB", "1", "1"),
        _edge_row("Q001-E02", "raterA", "0", "0"),
        _edge_row("Q001-E02", "raterB", "0", "0"),
        _edge_row("Q002-E01", "raterA", "1", "0"),
        _edge_row("Q002-E01", "raterB", "1", "0"),
    ]
    result = score_edge_ratings(rows)

    assert result["netmedex_hybrid_rag"]["edge_count"] == 6
    assert result["netmedex_hybrid_rag"]["biological_precision"] == pytest.approx(2 / 3, abs=1e-4)
    assert result["_inter_rater_agreement"]["kappa"]["biologically_meaningful"] == 1.0
    assert result["_inter_rater_agreement"]["kappa"]["relation_type_correct"] == 1.0
    assert result["_inter_rater_agreement"]["n_paired_edges"] == 3


def _hypothesis_row(qid, hid, system, rater_id, score):
    return {
        "system": system,
        "question_id": qid,
        "hypothesis_id": hid,
        "rater_id": rater_id,
        "novelty": score,
        "plausibility": score,
        "testability": score,
        "research_value": score,
    }


def test_score_mean_ratings_paired_comparison_between_two_systems():
    fields = ["novelty", "plausibility", "testability", "research_value"]
    rows = [
        _hypothesis_row("Q001", "Q001-A", "netmedex_hybrid_rag", "raterA", "5"),
        _hypothesis_row("Q001", "Q001-A", "netmedex_hybrid_rag", "raterB", "5"),
        _hypothesis_row("Q001", "Q001-B", "traditional_rag", "raterA", "3"),
        _hypothesis_row("Q001", "Q001-B", "traditional_rag", "raterB", "3"),
        _hypothesis_row("Q002", "Q002-A", "netmedex_hybrid_rag", "raterA", "4"),
        _hypothesis_row("Q002", "Q002-A", "netmedex_hybrid_rag", "raterB", "4"),
        _hypothesis_row("Q002", "Q002-B", "traditional_rag", "raterA", "4"),
        _hypothesis_row("Q002", "Q002-B", "traditional_rag", "raterB", "4"),
    ]
    result = score_mean_ratings(rows, fields)

    paired = result["_paired_comparison"]
    assert paired["systems"] == ["netmedex_hybrid_rag", "traditional_rag"]
    assert paired["n_questions"] == 2
    assert paired["mean_diff"] == 1.0  # (5-3 + 4-4) / 2
    assert paired["wins_first_system"] == 1
    assert paired["ties"] == 1
    assert result["_inter_rater_agreement"]["weighted_kappa"]["novelty"] == 1.0


def test_score_edge_verification_delta_pairs_by_question_not_edge_id():
    baseline = [
        _edge_row("Q001-E01", "raterA", "1", "0"),
        _edge_row("Q001-E02", "raterA", "1", "0"),
    ]
    verified = [
        # Different edge_ids than baseline (independent extraction run) -- must still pair by
        # the shared Q001 question_id, not by matching edge_id.
        _edge_row("Q001-E05", "raterA", "1", "1"),
        _edge_row("Q001-E06", "raterA", "1", "1"),
    ]
    result = score_edge_verification_delta(baseline, verified)

    assert result["relation_type_precision"]["n_shared_questions"] == 1
    assert result["relation_type_precision"]["mean_diff_verified_minus_baseline"] == 1.0


def test_score_edge_verification_delta_prefers_shared_edge_ids_when_available():
    baseline = [
        _edge_row("Q001-E01", "raterA", "0", "0"),
        _edge_row("Q001-E02", "raterA", "0", "0"),
    ]
    verified = [
        _edge_row("Q001-E01", "raterA", "1", "1"),
        _edge_row("Q001-E02", "raterA", "1", "1"),
    ]
    result = score_edge_verification_delta(baseline, verified)

    assert result["biological_precision"]["pairing_mode"] == "edge_id"
    assert result["biological_precision"]["n_shared_items"] == 2
    assert result["biological_precision"]["mean_diff_verified_minus_baseline"] == 1.0


def test_score_path_qrels_reports_2hop_metrics_and_negative_controls():
    qrels = [
        _path_qrel_row(
            "Q001",
            "Q001-P01",
            "A",
            "B",
            "C",
            "activates",
            "inhibits",
            "forward",
            "forward",
            "10;11",
            relevance="2",
        ),
        _path_qrel_row(
            "Q002",
            "Q002-P01",
            "X",
            "Y",
            "Z",
            "associated_with",
            "",
            "undirected",
            "",
            "",
            relevance="0",
            negative="1",
        ),
    ]
    runs = [
        _path_run_row(
            "netmedex_hybrid_rag",
            "Q001",
            1,
            "A",
            "B",
            "C",
            "activates",
            "inhibits",
            "forward",
            "forward",
            "10;11;12",
        )
    ]
    result = score_path_qrels(qrels, runs)["netmedex_hybrid_rag"]

    assert result["question_count"] == 2
    assert result["exact_path_precision_at_5"] == 0.5
    assert result["exact_path_recall"] == 0.5
    assert result["bridge_entity_f1"] == 0.5
    assert result["direction_accuracy"] == 0.5
    assert result["cross_document_synthesis_rate"] == 0.5
    assert result["negative_control_false_positive_rate"] == 0.0


def test_score_arm_exposures_flags_distinct_exposure_signatures():
    rows = [
        {
            "system": "netmedex_hybrid_rag",
            "arm": "A_text_only",
            "question_id": "Q001",
            "exposed_pmids": "1;2",
            "exposed_edges": "edge-a",
            "exposed_paths": "path-a",
            "exposure_signature": "sig-a",
        },
        {
            "system": "netmedex_hybrid_rag",
            "arm": "B_entity_validated",
            "question_id": "Q001",
            "exposed_pmids": "2;3",
            "exposed_edges": "edge-b",
            "exposed_paths": "path-b",
            "exposure_signature": "sig-b",
        },
    ]
    result = score_arm_exposures(rows)

    assert result["A_text_only"]["question_count"] == 1
    assert result["B_entity_validated"]["question_count"] == 1
    assert result["_pairwise_overlap"]["A_text_only__vs__B_entity_validated"]["signature_match_rate"] == 0.0
