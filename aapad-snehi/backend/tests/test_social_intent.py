from app.services.social_intent import classify_help_intent


def test_explicit_disaster_help_offer_matches():
    result = classify_help_intent(
        "Our team can help Assam flood response with food, boats and transport."
    )

    assert result.matched is True
    assert result.category == "explicit_offer"
    assert result.confidence == "high"
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


def test_active_assistance_and_institutional_support_are_included():
    active = classify_help_intent(
        "Our experts are providing psychological first aid to affected residents."
    )
    institutional = classify_help_intent(
        "Pakistan offers Nepal support amid the flood crisis."
    )

    assert active.matched is True
    assert active.category == "active_assistance"
    assert active.confidence == "medium"
    assert "medical" in active.capabilities
    assert institutional.matched is True
    assert institutional.category == "institutional_support"
    assert institutional.confidence == "medium"


def test_fundraising_and_relief_appeals_are_low_confidence_leads():
    donation = classify_help_intent(
        "A restaurant will donate ten percent of sales to Nepal flood relief."
    )
    appeal = classify_help_intent(
        "You can support affected families through the SOS Nepal appeal."
    )

    assert donation.matched is True
    assert donation.category == "fundraising_or_donation"
    assert donation.confidence == "low"
    assert appeal.matched is True
    assert appeal.confidence == "low"


def test_request_only_stays_excluded_but_mixed_operational_update_is_visible():
    request = classify_help_intent("Please send help; we need food after the flood.")
    mixed = classify_help_intent(
        "Families need food after the flood; our team is distributing meals."
    )

    assert request.matched is False
    assert request.category == "request_for_help"
    assert mixed.matched is True
    assert mixed.category == "explicit_offer"
    assert mixed.confidence == "high"
