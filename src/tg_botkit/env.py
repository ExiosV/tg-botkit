import os
from typing import Iterable, List


def missing_secrets(names: Iterable[str], environ=None) -> List[str]:
    """Names that are unset/empty or still the sealed-secret placeholder CHANGEME (human has not filled them in yet)."""
    environ = os.environ if environ is None else environ
    return [n for n in names if environ.get(n, "") in ("", "CHANGEME")]
