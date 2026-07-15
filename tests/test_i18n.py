"""The TUI ships a complete, safe translation for every advertised language."""

from __future__ import annotations

import re

from nyora_tui import i18n
from nyora_tui._translations import TRANSLATIONS

_PLACEHOLDER = re.compile(r"{[^}]+}")


def _tokens(s: str) -> set[str]:
    return set(_PLACEHOLDER.findall(s))


def test_every_ui_language_has_a_full_translation() -> None:
    # Every advertised language (except English, the base) ships translations
    # for the whole catalogue — no silent English gaps in the UI.
    advertised = {code for code, _name in i18n.UI_LANGUAGES if code != "en"}
    assert advertised <= set(TRANSLATIONS), advertised - set(TRANSLATIONS)
    for lang in advertised:
        missing = set(i18n.EN) - set(TRANSLATIONS[lang])
        assert not missing, f"{lang} missing {missing}"


def test_translations_preserve_placeholders() -> None:
    for lang, catalog in TRANSLATIONS.items():
        for key, text in catalog.items():
            assert _tokens(i18n.EN[key]) == _tokens(text), f"{lang}/{key} placeholder mismatch"


def test_translations_only_use_known_keys() -> None:
    known = set(i18n.EN)
    for lang, catalog in TRANSLATIONS.items():
        assert set(catalog) <= known, f"{lang} has unknown keys {set(catalog) - known}"


def test_t_switches_language_and_falls_back() -> None:
    i18n.set_language("ja")
    assert i18n.t("nav.library") == TRANSLATIONS["ja"]["nav.library"]
    i18n.set_language("en")
    assert i18n.t("nav.library") == i18n.EN["nav.library"]
    # unknown key and unknown language both degrade instead of raising
    assert i18n.t("no.such.key") == "no.such.key"
    i18n.set_language("xx-unknown")
    assert i18n.t("nav.library") == i18n.EN["nav.library"]
    i18n.set_language("en")


def test_t_format_is_crash_proof() -> None:
    assert i18n.t("welcome.signin_failed", error="boom").endswith("boom")
    # a missing field returns the template rather than raising
    assert "{error}" in i18n.t("welcome.signin_failed")


def test_regional_variant_falls_back_to_base() -> None:
    i18n.set_language("de-at")  # not a catalogue code -> base 'de'
    assert i18n.current_language() == "de"
    i18n.set_language("en")
