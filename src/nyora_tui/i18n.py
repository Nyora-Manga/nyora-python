"""Interface localisation for the Nyora terminal reader (TUI only).

The TUI's chrome — onboarding, navigation, menus, the reader and the library —
can be shown in ~40 languages. Only the *TUI* is localised: the SDK and CLI stay
English (they are developer surfaces). Translations live in
:mod:`nyora_tui._translations`; anything missing falls back to English, so the
UI never breaks on an incomplete locale.

Usage::

    from nyora_tui.i18n import t
    label = t("nav.library")
    msg = t("welcome.signin_failed", error=str(exc))

``t()`` never raises: an unknown key returns the key, and a missing/rejected
format argument returns the raw template. The active language is read once from
config (:func:`nyora.config.read_ui_lang`) and can be switched at runtime with
:func:`set_language`.
"""

from __future__ import annotations

# The base catalogue: every key with its English source string. This is the
# single source of truth for what text exists; translators fill the same keys.
EN: dict[str, str] = {
    # -- brand / welcome -----------------------------------------------------
    "app.tagline": "Manga, anywhere the night takes you",
    "welcome.headline": "Read like the world can wait.",
    "welcome.blurb": (
        "Nyora pulls hundreds of sources into one quiet shelf and remembers "
        "exactly where you stopped — on every device. Sign in to sync and back "
        "it up, or just start reading."
    ),
    "welcome.features": "Hundreds of sources  ·  Picks up on every device  ·  No ads, ever",
    "welcome.start_reading": "Start reading",
    "welcome.email": "Email",
    "welcome.password": "Password",
    "welcome.sign_in": "Sign in",
    "welcome.create_account": "Create account",
    "welcome.guest": "Continue as guest",
    "welcome.guest_hint": "No account needed — go in as a guest and sync whenever you like.",
    "welcome.enter_creds": "Enter your email and password.",
    "welcome.signing_in": "Signing in…",
    "welcome.welcome_back": "Welcome back.",
    "welcome.creating": "Creating your account…",
    "welcome.account_ready": "Account ready.",
    "welcome.signin_failed": "Sign-in failed: {error}",
    "welcome.signup_failed": "Sign-up failed: {error}",
    # -- onboarding preferences ---------------------------------------------
    "prefs.youre_in": "You’re in",
    "prefs.title": "Set up your shelf",
    "prefs.blurb": (
        "Choose your app language, colour theme and content preference — we’ll "
        "show the matching sources. You can change any of this later."
    ),
    "prefs.show_nsfw": "Show 18+ sources",
    "prefs.show_nsfw_hint": "Include adult-only sources in browse & search.",
    "prefs.app_language": "App language",
    "prefs.app_language_hint": "the language Nyora’s interface is shown in",
    "prefs.theme": "Colour theme",
    "prefs.theme_hint": "light or dark · change anytime later",
    "prefs.source_langs": "Source languages",
    "prefs.source_langs_hint": "space to toggle · none = all languages",
    "prefs.start_reading": "Start reading",
    # -- navigation / global chrome -----------------------------------------
    "nav.sources": "Sources",
    "nav.popular": "Popular",
    "nav.latest": "Latest",
    "nav.search": "Search",
    "nav.library": "Library",
    "nav.history": "History",
    "nav.downloads": "Downloads",
    "nav.account": "Account",
    "nav.keys": "Keys",
    "nav.theme": "Theme",
    "nav.language": "Language",
    "nav.quit": "Quit",
    "nav.back": "Back",
    "nav.home": "Home",
    "nav.open": "Open",
    "nav.settings": "Settings",
    # -- toasts / status -----------------------------------------------------
    "toast.not_installed": "That source isn’t installed here.",
    "toast.added": "Added to library.",
    "toast.removed": "Removed from library.",
    "toast.syncing": "syncing with cloud…",
    # -- common --------------------------------------------------------------
    "common.loading": "Loading…",
    "common.no_results": "Nothing here yet.",
    "common.search_placeholder": "Search…",
    "common.all_languages": "All languages",
    "common.more_pages": "more pages available",
    "common.cancel": "Cancel",
    "common.apply": "Apply",
    "common.close": "Close",
    "common.working": "Working…",
    "common.failed": "Something went wrong.",
    # -- reader --------------------------------------------------------------
    "reader.next_chapter": "Next chapter",
    "reader.prev_chapter": "Previous chapter",
    "reader.mode": "Mode",
    "reader.fit": "Fit",
    "reader.download": "Download",
    "reader.no_next": "No next chapter.",
    "reader.no_prev": "No previous chapter.",
    "reader.resolving": "resolving pages…",
    "reader.downloading": "Downloading {title}…",
    "reader.saved": "Saved {name}",
    "reader.offline": "offline",
    "reader.already_downloaded": "This chapter is already downloaded.",
    "reader.nothing_to_download": "Nothing to download yet.",
    "reader.no_offline_pages": "No downloaded pages found on disk.",
    "details.loading": "loading…",
    "details.chapters": "chapters",
    # -- library / history / downloads --------------------------------------
    "library.title": "Library",
    "library.empty": "No favourites yet. Open a title and press f to add it.",
    "library.favourites": "Favourites",
    "history.title": "History",
    "history.empty": "No history yet. Read a chapter and it shows up here.",
    "downloads.title": "Downloads",
    "downloads.empty": "No downloads yet. Press d on a chapter to download it.",
    "downloads.read_offline": "Read offline",
    # -- source browser / language navigator --------------------------------
    "sources.title": "Sources",
    "sources.filter": "type to filter sources…",
    "langnav.title": "Jump to language",
    "langnav.hint": "type to filter · enter to jump",
    "langnav.count": "{count} sources",
    # -- theme picker --------------------------------------------------------
    "theme.title": "Colour scheme",
    "theme.hint": "↑↓ preview · enter apply · esc cancel",
    "theme.light": "Light",
    "theme.dark": "Dark",
    # -- account -------------------------------------------------------------
    "account.title": "Account",
    "account.signed_in_as": "Signed in as {email}",
    "account.guest": "Guest — not signed in",
    "account.sign_out": "Sign out",
    "account.sign_in": "Sign in",
    "account.synced": "Library synced.",
    # -- keybindings help ----------------------------------------------------
    "keys.title": "Keyboard shortcuts",
    "keys.hint": "press ? or esc to close",
}

# ``(code, endonym)`` — the languages the interface can be shown in, labelled in
# their own script so the picker reads naturally whatever the current UI locale.
# Codes match the source-language codes the engine reports.
UI_LANGUAGES: list[tuple[str, str]] = [
    ("en", "English"),
    ("ja", "日本語"),
    ("zh", "简体中文"),
    ("zh-hant", "繁體中文"),
    ("ko", "한국어"),
    ("es", "Español"),
    ("es-419", "Español (LatAm)"),
    ("fr", "Français"),
    ("pt", "Português"),
    ("pt-br", "Português (BR)"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("ru", "Русский"),
    ("uk", "Українська"),
    ("pl", "Polski"),
    ("nl", "Nederlands"),
    ("id", "Bahasa Indonesia"),
    ("ms", "Bahasa Melayu"),
    ("vi", "Tiếng Việt"),
    ("th", "ไทย"),
    ("tr", "Türkçe"),
    ("ar", "العربية"),
    ("fa", "فارسی"),
    ("he", "עברית"),
    ("hi", "हिन्दी"),
    ("bn", "বাংলা"),
    ("ta", "தமிழ்"),
    ("ne", "नेपाली"),
    ("cs", "Čeština"),
    ("sk", "Slovenčina"),
    ("sl", "Slovenščina"),
    ("hu", "Magyar"),
    ("ro", "Română"),
    ("el", "Ελληνικά"),
    ("bg", "Български"),
    ("sr", "Српски"),
    ("sq", "Shqip"),
    ("ca", "Català"),
    ("sv", "Svenska"),
    ("no", "Norsk"),
    ("da", "Dansk"),
    ("fi", "Suomi"),
]

#: Right-to-left UI locales (for future bidi tweaks / display only).
RTL_LANGS = frozenset({"ar", "fa", "he"})

_ENDONYMS = dict(UI_LANGUAGES)


def available_languages() -> list[tuple[str, str]]:
    """The ``(code, endonym)`` languages the interface can be displayed in."""
    return list(UI_LANGUAGES)


def language_name(code: str) -> str:
    """Endonym for a UI language code (falls back to the code itself)."""
    return _ENDONYMS.get(code, code)


def _load_translations() -> dict[str, dict[str, str]]:
    try:
        from nyora_tui._translations import TRANSLATIONS

        return TRANSLATIONS if isinstance(TRANSLATIONS, dict) else {}
    except Exception:  # noqa: BLE001 - translations module optional/absent
        return {}


_TRANSLATIONS = _load_translations()
_current = "en"


def _normalise(code: str | None) -> str:
    """Map a config/locale code to a catalogue language ('' or unknown -> 'en')."""
    if not code:
        return "en"
    code = code.strip().lower()
    if code in _ENDONYMS:
        return code
    # Fall back from a regional variant to its base (e.g. 'de-at' -> 'de').
    base = code.split("-", 1)[0]
    return base if base in _ENDONYMS else "en"


def set_language(code: str | None) -> None:
    """Set the active UI language for subsequent :func:`t` calls."""
    global _current
    _current = _normalise(code)


def current_language() -> str:
    """The active UI language code."""
    return _current


def init_from_config() -> str:
    """Load the persisted UI language into the active language; returns it."""
    from nyora.config import read_ui_lang

    set_language(read_ui_lang())
    return _current


def t(key: str, /, **kwargs: object) -> str:
    """Translate ``key`` into the active language, formatting with ``kwargs``.

    Resolution order: active-language catalogue → English catalogue → the key
    itself. Never raises — a bad/missing format field yields the unformatted
    template, so a malformed translation degrades instead of crashing the UI.
    """
    template = _TRANSLATIONS.get(_current, {}).get(key) or EN.get(key) or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template
