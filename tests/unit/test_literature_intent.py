import pytest

from app import requires_live_literature, selected_skill


@pytest.mark.parametrize("query", [
    "According to the local calibration SOP, what bioimpedance reference resistor is used?",
    "How does the reference electrode work?",
    "What are you doing?",
    "Explain the reference voltage.",
    "Can you change the wallpapers?",
])
def test_non_bibliographic_words_do_not_trigger_public_search(query):
    assert not requires_live_literature(query)
    assert selected_skill(query) != "literature"


@pytest.mark.parametrize("query", [
    "Find papers about reference electrodes.",
    "Give me references for Bio-Z calibration.",
    "Find the DOI of this paper.",
    "查找 Bio-Z 参考电极的论文",
])
def test_explicit_paper_request_still_routes_to_literature(query):
    assert requires_live_literature(query)
    assert selected_skill(query) == "literature"

