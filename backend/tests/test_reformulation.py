from main import needs_reformulation

def test_short_question_needs_reformulation():
    assert needs_reformulation("what about it") is True

def test_long_specific_question_with_pronoun_still_triggers_reformulation():
    # Known trade-off: "it" triggers reformulation even in self-contained questions.
    # This costs one extra API call but avoids the worse failure mode of missing
    # a real follow-up question and searching with unclear context.
    assert needs_reformulation("What is a key-value store and how does it differ from a document database?") is True

def test_long_specific_question_without_trigger_words_skips_reformulation():
    assert needs_reformulation("Explain the architecture terms used in key-value databases") is False

def test_pronoun_triggers_reformulation():
    assert needs_reformulation("tell me more about that") is True