"""Lightweight gettext-based i18n shim, replacing Flask-Babel at runtime.

Reads the existing compiled translations/{hi,te}/LC_MESSAGES/messages.mo files
directly via stdlib gettext. The `pybabel extract/update/compile` workflow
(Babel package, dev-only) remains how those .mo files get maintained.
"""

import gettext as _gettext_module
from contextvars import ContextVar

LANGUAGES = {"en": "English", "hi": "हिन्दी", "te": "తెలుగు"}
DEFAULT_LOCALE = "en"
TRANSLATIONS_DIR = "translations"
DOMAIN = "messages"

current_locale: ContextVar[str] = ContextVar("current_locale", default=DEFAULT_LOCALE)

_translations: dict[str, _gettext_module.NullTranslations] = {}


def _translation(locale):
    if locale not in _translations:
        try:
            _translations[locale] = _gettext_module.translation(
                DOMAIN, TRANSLATIONS_DIR, languages=[locale]
            )
        except FileNotFoundError:
            _translations[locale] = _gettext_module.NullTranslations()
    return _translations[locale]


def get_locale():
    return current_locale.get()


def set_locale(locale):
    if locale not in LANGUAGES:
        locale = DEFAULT_LOCALE
    current_locale.set(locale)
    return locale


def _best_match(accept_language_header, available):
    """Pick the best-matching language code from an Accept-Language header."""
    candidates = []
    for part in accept_language_header.split(","):
        part = part.strip()
        if not part:
            continue
        tag, _sep, q = part.partition(";q=")
        try:
            quality = float(q) if q else 1.0
        except ValueError:
            quality = 1.0
        candidates.append((tag.strip().split("-")[0].lower(), quality))
    for tag, _quality in sorted(candidates, key=lambda c: c[1], reverse=True):
        if tag in available:
            return tag
    return None


def resolve_locale(request):
    """Mirror Flask-Babel's locale_selector: session "lang", then Accept-Language."""
    lang = request.session.get("lang")
    if lang in LANGUAGES:
        return lang
    accept_language = request.headers.get("accept-language", "")
    return _best_match(accept_language, LANGUAGES) or DEFAULT_LOCALE


def gettext(message, **variables):
    translated = _translation(get_locale()).gettext(message)
    return translated % variables if variables else translated


def ngettext(singular, plural, num, **variables):
    variables.setdefault("num", num)
    translated = _translation(get_locale()).ngettext(singular, plural, num)
    return translated % variables


class LazyString:
    """Resolves to a translated string at str()-time, using the current locale.

    Needed because constants.py / parking_engine.py build label dicts at import
    time, before any request (and thus any locale) exists.
    """

    def __init__(self, func_, *args, **kwargs):
        self._func = func_
        self._args = args
        self._kwargs = kwargs

    def __str__(self):
        return self._func(*self._args, **self._kwargs)

    def __repr__(self):
        return repr(str(self))

    def __eq__(self, other):
        return str(self) == str(other)

    def __ne__(self, other):
        return str(self) != str(other)

    def __hash__(self):
        return hash(str(self))

    def __add__(self, other):
        return str(self) + other

    def __radd__(self, other):
        return other + str(self)

    def __mod__(self, other):
        return str(self) % other


def lazy_gettext(message, **variables):
    return LazyString(gettext, message, **variables)


_ = gettext
_l = lazy_gettext
