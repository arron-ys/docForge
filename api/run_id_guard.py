from __future__ import annotations

import re

from .errors import invalid_run_id

RUN_ID_PATTERN = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-f0-9]{4}$")


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise invalid_run_id()
    return run_id
