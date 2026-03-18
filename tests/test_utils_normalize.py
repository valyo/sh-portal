"""Tests for normalize_customer_name (utils)."""

import pytest


class TestNormalizeCustomerName:
    """Tests for normalize_customer_name."""

    def test_empty_string_returns_none(self):
        from sh_portal.utils import normalize_customer_name
        assert normalize_customer_name('') is None
        assert normalize_customer_name('   ') is None

    def test_none_returns_none(self):
        from sh_portal.utils import normalize_customer_name
        assert normalize_customer_name(None) is None

    def test_not_string_returns_none(self):
        from sh_portal.utils import normalize_customer_name
        assert normalize_customer_name(123) is None
        assert normalize_customer_name([]) is None

    def test_trims_and_collapses_whitespace(self):
        from sh_portal.utils import normalize_customer_name
        assert normalize_customer_name('  john   doe  ') == 'John Doe'

    def test_title_cases_each_word(self):
        from sh_portal.utils import normalize_customer_name
        assert normalize_customer_name('JOHN DOE') == 'John Doe'
        assert normalize_customer_name('john doe') == 'John Doe'
        assert normalize_customer_name('anders andersson') == 'Anders Andersson'
