import uuid

from app.retrieval.fusion import reciprocal_rank_fusion


def test_single_list_passthrough_preserves_order() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    fused = reciprocal_rank_fusion([[a, b, c]])

    assert [chunk_id for chunk_id, _ in fused] == [a, b, c]


def test_disjoint_rankings_tie_when_both_ranked_first_in_their_own_leg() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()

    fused = dict(reciprocal_rank_fusion([[a], [b]]))

    assert fused[a] == fused[b]


def test_chunk_appearing_in_both_legs_outranks_a_chunk_in_only_one() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    # a is ranked #1 in both legs; b and c are each ranked #1 in only one leg.
    fused = reciprocal_rank_fusion([[a, b], [a, c]])

    assert fused[0][0] == a


def test_chunk_absent_from_a_leg_only_scores_from_legs_it_appears_in() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()

    fused = dict(reciprocal_rank_fusion([[a], [a, b]], k=60))

    assert fused[a] == 1 / 61 + 1 / 61  # rank 1 in both legs
    assert fused[b] == 1 / 62  # rank 2 in the second leg only


def test_smaller_k_increases_scores_but_preserves_relative_order() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()

    fused_default = dict(reciprocal_rank_fusion([[a, b]]))
    fused_small_k = dict(reciprocal_rank_fusion([[a, b]], k=1))

    assert fused_default[a] > fused_default[b]
    assert fused_small_k[a] > fused_small_k[b]
    assert fused_small_k[a] > fused_default[a]


def test_empty_rankings_returns_empty() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[]]) == []
