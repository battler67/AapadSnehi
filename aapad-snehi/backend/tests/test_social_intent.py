from app.services.social_intent import classify_help_intent


def test_explicit_disaster_help_offer_matches():
    result = classify_help_intent(
        "Our team can help Assam flood response with food, boats and transport."
    )

    assert result.matched is True
    assert "can help" in result.matched_terms
    assert {"food", "rescue", "transport"}.issubset(result.capabilities)


def test_request_for_help_does_not_match_an_offer():
    result = classify_help_intent(
        "We need urgent help, food and rescue after the Assam flood."
    )

    assert result.matched is False


def test_negated_and_generic_positive_posts_do_not_match():
    assert classify_help_intent("We cannot help with flood rescue today.").matched is False
    assert classify_help_intent("Great news and positive vibes for everyone!").matched is False
