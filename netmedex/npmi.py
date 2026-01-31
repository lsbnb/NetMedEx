from __future__ import annotations

import math

MIN_EDGE_WIDTH = 0
MAX_EDGE_WIDTH = 20


def normalized_pointwise_mutual_information(
    n_x: float,
    n_y: float,
    n_xy: float,
    N: int,
    n_threshold: int,
    below_threshold_default: float = MIN_EDGE_WIDTH / MAX_EDGE_WIDTH,
):
    # Defensive checks: avoid log2(0) or log2(negative) which cause math domain errors
    if n_x <= 0 or n_y <= 0 or n_xy <= 0 or N <= 0:
        return below_threshold_default
    
    if n_xy == 0:
        npmi = -1
    elif (n_xy / N) == 1:
        npmi = 1
    else:
        # Additional safety check to ensure we don't compute log of 0
        p_x = n_x / N
        p_y = n_y / N
        p_xy = n_xy / N
        
        if p_x <= 0 or p_y <= 0 or p_xy <= 0:
            return below_threshold_default
        
        npmi = -1 + (math.log2(p_x) + math.log2(p_y)) / math.log2(p_xy)

    # non-normalized
    # pmi = math.log2(p_x) + math.log2(p_y) - math.log2(p_xy)

    if n_x < n_threshold or n_y < n_threshold:
        npmi = min(npmi, below_threshold_default)

    return npmi
