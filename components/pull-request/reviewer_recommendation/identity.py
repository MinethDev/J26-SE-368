"""Account identity helpers: login normalization and bot detection."""


# Accounts typed as "User" in the dataset that behave as automation.
# Pending confirmation; extend this set rather than special-casing elsewhere.
KNOWN_BOT_LOGINS = frozenset({
    "matticbot",
    "azclibot",
})

_MISSING_VALUES = {"", "nan", "none", "null"}


def normalize_login(login):
    """Return a stripped login, or None when the login is missing."""

    if login is None:
        return None

    login = str(login).strip()

    if login.lower() in _MISSING_VALUES:
        return None

    return login


def is_bot(login, account_type=None) -> bool:
    """Identify automation accounts by type, GitHub bot suffix, or known list."""

    if account_type is not None and str(account_type).strip() == "Bot":
        return True

    login = normalize_login(login)

    if login is None:
        return False

    login = login.lower()

    return login.endswith("[bot]") or login in KNOWN_BOT_LOGINS


def same_login(first, second) -> bool:
    """Compare two logins case-insensitively (GitHub logins are case-insensitive)."""

    first = normalize_login(first)
    second = normalize_login(second)

    if first is None or second is None:
        return False

    return first.lower() == second.lower()
