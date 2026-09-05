from rules.rule_engine import check_regex, check_expiry, check_cross_match, load_rules, validate_document


def test_gstin_regex_valid():
    assert check_regex("27ABCPL1234F1Z5", r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


def test_gstin_regex_invalid():
    assert not check_regex("INVALID123", r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")


def test_expiry_future_date_passes():
    assert check_expiry("09-Jan-2030")


def test_expiry_past_date_fails():
    assert not check_expiry("31-Mar-2024")


def test_cross_match_ignores_suffix_differences():
    assert check_cross_match("Bharat Enterprises Pvt Ltd", "Bharat Enterprises Private Limited")


def test_cross_match_catches_real_mismatch():
    assert not check_cross_match("Sunrise Traders Pvt Ltd", "Sunrise Trading Company")