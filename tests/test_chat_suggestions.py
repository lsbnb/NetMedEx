from webapp.callbacks.chat_callbacks import parse_suggestions


def test_parse_suggestions_google_loose_header_does_not_fragment_to_and():
    content = (
        "### Evidence-Based Answer\n"
        "BRCA1 is associated with breast neoplasms.\n\n"
        "Suggested Questions: These will focus on the specifics of the cohorts, "
        "the nature of the BRCA1 association (mutations vs. expression), and "
        "the next highest-value validation experiment.\n"
    )

    suggestions, _ = parse_suggestions(content)

    assert len(suggestions) == 3
    assert all(s.strip().lower() not in {"and", "or"} for s in suggestions)


def test_parse_suggestions_explicit_q_format_kept():
    content = (
        "3. Suggested Follow-up Questions\n"
        "[Q1: What evidence supports BRCA1 causality?]\n"
        "[Q2: Which PMIDs provide mechanistic links?]\n"
        "[Q3: What should be validated next?]\n"
    )

    suggestions, _ = parse_suggestions(content)

    assert suggestions == [
        "What evidence supports BRCA1 causality",
        "Which PMIDs provide mechanistic links",
        "What should be validated next",
    ]


def test_parse_suggestions_markdown_bold_formats():
    test_cases = [
        (
            "Suggested Questions:\nQ1: What model? Q2: How might? Q3: What gap?",
            ["What model", "How might", "What gap"]
        ),
        (
            "Suggested Questions:\n**Q1:** What model? **Q2:** How might? **Q3:** What gap?",
            ["What model", "How might", "What gap"]
        ),
        (
            "Suggested Questions:\n**Q1**: What model? **Q2**: How might? **Q3**: What gap?",
            ["What model", "How might", "What gap"]
        ),
        (
            "Suggested Questions:\n[Q1: What model?] [Q2: How might?] [Q3: What gap?]",
            ["What model", "How might", "What gap"]
        ),
        (
            "Suggested Questions:\n[**Q1**: What model?] [**Q2**: How might?] [**Q3**: What gap?]",
            ["What model", "How might", "What gap"]
        ),
        (
            "Suggested Questions:\n[**Q1:** What model?] [**Q2:** How might?] [**Q3:** What gap?]",
            ["What model", "How might", "What gap"]
        ),
        (
            "Suggested Questions:\n**[Q1]**: What model? **[Q2]**: How might? **[Q3]**: What gap?",
            ["What model", "How might", "What gap"]
        ),
        (
            "Suggested Questions:\n**[Q1]:** What model? **[Q2]:** How might? **[Q3]:** What gap?",
            ["What model", "How might", "What gap"]
        ),
        (
            "Suggested Questions:\n[Q1]: What model? [Q2]: How might? [Q3]: What gap?",
            ["What model", "How might", "What gap"]
        ),
        (
            "Suggested Questions:\n[**Q1**]: What model? [**Q2**]: How might? [**Q3**]: What gap?",
            ["What model", "How might", "What gap"]
        ),
    ]

    for tc, expected in test_cases:
        suggestions, before = parse_suggestions(tc)
        assert suggestions == expected
        assert before == "Suggested Questions:"
