from faq_search import search_faq


def test_search_faq_finds_a_close_match():
    result = search_faq("how do I switch between my properties", lang="en")
    assert result is not None
    assert "switch" in result["question"].lower()


def test_search_faq_returns_none_for_unrelated_query():
    assert search_faq("asdkjaslkdjaslkdj nonsense gibberish query", lang="en") is None


def test_search_faq_works_in_hindi():
    result = search_faq("मैं भाषा कैसे बदलूं", lang="hi")
    assert result is not None
    assert "भाषा" in result["question"]
