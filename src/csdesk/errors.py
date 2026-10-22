"""Errors whose message is meant to be read by her (or by Claude on her behalf)."""


class CsDeskError(Exception):
    """Base class. The message says what went wrong and what to do next."""


class NotFound(CsDeskError):
    """A company, person, document or filing that isn't in the company file."""


class Invalid(CsDeskError, ValueError):
    """A value that fails a format or consistency check (a mistyped PAN, a CIN with a missing digit)."""


class Blocked(CsDeskError):
    """An action reserved for her: submit, sign, pay. The tools never do these."""


class PageChanged(CsDeskError):
    """The portal page no longer matches the recorded form recipe; stop before typing anything else."""
