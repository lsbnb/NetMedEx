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
    if n_xy == 0:
        npmi = -1
    elif (n_xy / N) == 1:
        npmi = 1
    else:
        npmi = -1 + (math.log2(n_x / N) + math.log2(n_y / N)) / math.log2(n_xy / N)

    # non-normalized
    # pmi = math.log2(p_x) + math.log2(p_y) - math.log2(p_xy)

    if n_x < n_threshold or n_y < n_threshold:
        npmi = min(npmi, below_threshold_default)

    return npmi
