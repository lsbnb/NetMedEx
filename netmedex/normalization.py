import logging
from collections import defaultdict

import networkx as nx
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

# Node types that require a much stricter threshold to prevent merging paralog genes,
# protein isoforms, and mutation variants (e.g. ALDH1A3 vs ALDH1A1, H3.1 K27M vs H3.3 K27M).
_PROTECTED_TYPES = {"Gene", "ProteinMutation", "DNAMutation", "SNP"}

# Threshold for protected types. Near-identity required (~1-2 character difference threshold).
_GENE_THRESHOLD = 0.995


def normalize_knowledge_graph(
    G: nx.Graph, llm_client, threshold: float = 0.96, progress_callback=None
):
    """
    Normalizes a Knowledge Graph by merging semantically similar nodes using sapBERT-style embeddings.

    Args:
        G: NetworkX Graph object
        llm_client: LLM client for fetching embeddings (must have get_embeddings method)
        threshold: Cosine similarity threshold for non-gene node merging (default 0.96)
        progress_callback: Optional callback for reporting progress (current, total, status, error)

    Returns:
        nx.Graph: The normalized graph

    Notes:
        Gene, ProteinMutation, DNAMutation, and SNP nodes always use a stricter threshold
        (_GENE_THRESHOLD = 0.995) to prevent merging paralog genes and protein isoforms.
        Cross-type merges (e.g. Disease node vs Gene node) are never performed in the
        vector-similarity pass.
    """
    if G.number_of_nodes() == 0:
        return G

    # 1. Extract node names for embedding and initial case-pass
    logger.info("Preparing metadata for normalization...")
    node_ids = list(G.nodes())
    node_data_list = [G.nodes[node_id] for node_id in node_ids]
    display_names = [data.get("name", node_id) for node_id, data in zip(node_ids, node_data_list)]
    node_types = [data.get("type", "unknown") for data in node_data_list]
    node_cuis = [data.get("mesh") for data in node_data_list]
    node_cuis = [c if c and str(c).strip() else None for c in node_cuis]

    merging_map = {}

    # 1.5 Case-Insensitive Pass: Merge identical names regardless of case.
    # For protected types (Gene etc.), only merge within the same type to avoid
    # collapsing e.g. a gene and a disease that happen to share a name (e.g. SHH).
    name_to_id = defaultdict(list)
    for i, name in enumerate(display_names):
        norm_name = name.strip().lower()
        name_to_id[norm_name].append(i)

    for indices in name_to_id.values():
        if len(indices) < 2:
            continue

        # Group by type for protected nodes; merge freely for non-protected.
        protected_in_group = [idx for idx in indices if node_types[idx] in _PROTECTED_TYPES]
        unprotected_in_group = [idx for idx in indices if node_types[idx] not in _PROTECTED_TYPES]

        # Merge protected-type duplicates only within the same subtype
        type_buckets = defaultdict(list)
        for idx in protected_in_group:
            type_buckets[node_types[idx]].append(idx)
        for bucket in type_buckets.values():
            if len(bucket) > 1:
                canonical_idx = bucket[0]
                for idx in bucket:
                    if node_cuis[idx]:
                        canonical_idx = idx
                        break
                canonical_nid = node_ids[canonical_idx]
                for idx in bucket:
                    if idx != canonical_idx:
                        merging_map[node_ids[idx]] = canonical_nid

        # Merge unprotected duplicates (Disease, Chemical, ENTITY, etc.) freely
        if len(unprotected_in_group) > 1:
            canonical_idx = unprotected_in_group[0]
            for idx in unprotected_in_group:
                if node_cuis[idx]:
                    canonical_idx = idx
                    break
            canonical_nid = node_ids[canonical_idx]
            for idx in unprotected_in_group:
                if idx != canonical_idx:
                    merging_map[node_ids[idx]] = canonical_nid

    if progress_callback:
        progress_callback(1, 5, "Metadata analysis complete.", None)

    # 2. Fetch embeddings for all node display names
    total_nodes = len(node_ids)
    logger.info(f"Fetching embeddings for {total_nodes} identifiers via {llm_client.provider}...")
    if progress_callback:
        progress_callback(2, 5, f"Fetching embeddings for {total_nodes} nodes...", None)

    try:
        embeddings = llm_client.get_embeddings(display_names)
    except Exception as e:
        logger.error(f"Failed to fetch embeddings: {e}")
        if progress_callback:
            progress_callback(2, 5, "Embedding failed (skipping vector normalization)", e)
        return G

    if not embeddings or len(embeddings) != total_nodes:
        logger.warning("Embedding result count mismatch. Skipping vector normalization.")
        return G

    # 3. Compute Similarity and Find Clusters
    if progress_callback:
        progress_callback(3, 5, "Computing similarity clusters...", None)

    embeddings_array = np.array(embeddings)
    sim_matrix = cosine_similarity(embeddings_array)

    processed_indices = set()

    for i in range(len(node_ids)):
        nid = node_ids[i]
        if i in processed_indices or nid in merging_map:
            continue

        type_i = node_types[i]
        is_protected_i = type_i in _PROTECTED_TYPES
        # Use stricter threshold for protected node types
        effective_threshold = _GENE_THRESHOLD if is_protected_i else threshold

        similar_indices = np.where(sim_matrix[i] > effective_threshold)[0]

        # --- SAME-TYPE GUARD ---
        # Never merge a Gene into a Disease or vice-versa, even at high similarity.
        # Keep only candidates whose type matches node i (or is unknown).
        def _types_compatible(t1: str, t2: str) -> bool:
            if t1 == t2:
                return True
            # Allow unknown/untyped nodes to merge with anything
            if t1 == "unknown" or t2 == "unknown":
                return True
            # Protected types never merge with non-protected types
            if (t1 in _PROTECTED_TYPES) != (t2 in _PROTECTED_TYPES):
                return False
            return True

        similar_indices = np.array(
            [idx for idx in similar_indices if _types_compatible(type_i, node_types[idx])]
        )

        if len(similar_indices) > 1:
            # --- CONFLICT RESOLUTION LOGIC ---
            cui_groups = defaultdict(list)
            for idx in similar_indices:
                cui_groups[node_cuis[idx]].append(idx)

            non_null_cuis = [c for c in cui_groups.keys() if c is not None]

            if len(non_null_cuis) > 1:
                # CONFLICT: Different expert CUIs — merge only within each CUI group
                for group in cui_groups.values():
                    if len(group) > 1:
                        canonical_idx = group[0]
                        for idx in group[1:]:
                            merging_map[node_ids[idx]] = node_ids[canonical_idx]
                            processed_indices.add(idx)
            else:
                # NO CONFLICT: pick canonical by CUI presence, then index order
                if non_null_cuis:
                    canonical_cui = non_null_cuis[0]
                    canonical_idx = cui_groups[canonical_cui][0]
                else:
                    canonical_idx = i

                canonical_name_id = node_ids[canonical_idx]
                for idx in similar_indices:
                    if idx != canonical_idx:
                        merging_map[node_ids[idx]] = canonical_name_id
                        processed_indices.add(idx)

        processed_indices.add(i)

    if not merging_map:
        logger.info("No redundant nodes found. Graph is already normalized.")
        if progress_callback:
            progress_callback(5, 5, "Normalization complete (no merges needed)", None)
        return G

    # Log breakdown: case vs semantic merges
    case_merges = sum(
        1 for src, tgt in merging_map.items()
        if display_names[node_ids.index(src)].lower() == display_names[node_ids.index(tgt)].lower()
        if src in node_ids and tgt in node_ids
    )
    merged_count = len(merging_map)
    logger.info(
        f"Merging {merged_count} redundant nodes "
        f"(case-only: ~{case_merges}, semantic: ~{merged_count - case_merges})..."
    )
    if progress_callback:
        progress_callback(4, 5, f"Merging {merged_count} redundant nodes...", None)

    # 4. Perform the Merge in NetworkX
    new_G = nx.Graph(**G.graph)

    for node, data in G.nodes(data=True):
        target = merging_map.get(node, node)
        if not new_G.has_node(target):
            new_G.add_node(target, **data)
        else:
            if "pmids" in data:
                new_G.nodes[target]["pmids"].update(data["pmids"])

    if progress_callback:
        progress_callback(4, 5, "Updating edge references...", None)

    for u, v, data in G.edges(data=True):
        u_new = merging_map.get(u, u)
        v_new = merging_map.get(v, v)

        if u_new == v_new:
            continue  # Skip self-loops created by merging

        if new_G.has_edge(u_new, v_new):
            new_G.edges[u_new, v_new]["relations"].update(data.get("relations", {}))
            if "confidences" in data:
                if "confidences" not in new_G.edges[u_new, v_new]:
                    new_G.edges[u_new, v_new]["confidences"] = {}
                new_G.edges[u_new, v_new]["confidences"].update(data["confidences"])
        else:
            new_G.add_edge(u_new, v_new, **data)

    logger.info(
        f"Normalization complete. Reduced node count from {total_nodes} to {new_G.number_of_nodes()}."
    )
    if progress_callback:
        progress_callback(5, 5, f"Normalization complete: {merged_count} nodes merged.", None)

    return new_G
