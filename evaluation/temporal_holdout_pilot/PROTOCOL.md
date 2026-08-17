# Temporal Holdout Feasibility Protocol

This is an internal retrospective feasibility pilot, not human-expert validation and not a
confirmatory discovery benchmark.

1. Build each discovery corpus only from PubMed records dated no later than 2015-12-31.
2. Retrieve source-, target-, and endpoint-pair neighborhoods independently. Query strings must
   not contain the candidate mediator names listed in `query_spec_v1.json`.
3. Use only the frozen pre-2016 corpus to build the semantic graph and generate candidate paths.
4. Freeze candidate A-B-C paths, relations, directions, supporting PMIDs, and corpus checksums
   before opening any 2016-2025 validation records.
5. Exclude a candidate when a pre-2016 endpoint-pair publication already directly states the
   predicted A-C relationship. Absence means no eligible record was found by the frozen query,
   not proof that no publication exists anywhere.
6. Search the 2016-2025 window only after candidate freeze. A validation hit must experimentally
   test the predicted A-C relationship; reviews, co-mentions, and purely computational predictions
   do not count as confirmation.
7. A provider-diverse blinded AI proxy reviewer may provisionally label validation evidence, but
   every output must state `human_expert_review_claimed=false`.
8. Report candidate yield, eligible hidden-link count, later experimental confirmation rate,
   contradictory evidence rate, and years-to-confirmation. Report all denominators, including
   zero-path and pre-existing-direct-link cases.
