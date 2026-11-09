from claim_replay.budget import CUT_MARK, clip, estimate_tokens, pack


def test_estimate_rounds_up():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abc") == 1
    assert estimate_tokens("a" * 35) == 10


def test_clip_leaves_short_text_alone():
    assert clip("short text", 100) == "short text"


def test_clip_keeps_more_of_the_start_and_fits():
    text = "S" * 5_000 + "E" * 5_000
    out = clip(text, 500)
    assert estimate_tokens(out) <= 500
    head, _, tail = out.partition(CUT_MARK)
    assert head.startswith("S") and tail.endswith("E")
    assert len(head) > len(tail) > 0


def test_pack_keeps_order_and_respects_budget():
    blocks = [f"block {i} " + "x" * 60 for i in range(10)]
    chunks = pack(blocks, 60)
    assert len(chunks) > 1
    assert all(estimate_tokens(c) <= 60 for c in chunks)
    assert "\n\n".join(chunks) == "\n\n".join(blocks)  # nothing lost, nothing reordered


def test_pack_clips_an_oversized_block_into_its_own_chunk():
    chunks = pack(["small", "B" * 2_000, "tail"], 100)
    assert chunks[0] == "small" and chunks[-1] == "tail"
    assert CUT_MARK in chunks[1] and estimate_tokens(chunks[1]) <= 100


def test_pack_of_nothing_is_one_empty_chunk():
    assert pack([], 100) == [""]
