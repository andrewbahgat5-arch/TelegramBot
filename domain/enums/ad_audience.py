"""Advertisement audience targeting (MASTER_PLAN Sprint 9.5, D-043).

First-class targeting: an ad has an ``audience_mode`` and zero or more
``ad_audience_rules``. Each rule has an ``effect`` (include/exclude) and a
``dimension`` (role / plan / language / user_id / segment / country) with a value.

Evaluation semantics (LOCKED, §23 Sprint 9.5):
* within a dimension, values are OR-ed;
* across dimensions, the matches are AND-ed;
* ``exclude`` removes a matching user ("all users except premium").
"""

from __future__ import annotations

from enum import StrEnum


class AudienceMode(StrEnum):
    """``advertisements.audience_mode``."""

    ALL = "all"  # everyone (still subject to the global Owner/premium exemptions)
    INCLUDE = "include"  # only users matching the include expression
    EXCLUDE = "exclude"  # everyone except users matching the exclude expression


class AudienceEffect(StrEnum):
    """``ad_audience_rules.effect``."""

    INCLUDE = "include"
    EXCLUDE = "exclude"


class AudienceDimension(StrEnum):
    """``ad_audience_rules.dimension``."""

    ROLE = "role"  # owner / moderator / user
    PLAN = "plan"  # free / premium (effective plan)
    LANGUAGE = "language"  # BCP-47 code
    USER_ID = "user_id"  # explicit telegram user id (user row id)
    SEGMENT = "segment"  # audience_segments.id
    COUNTRY = "country"  # reserved (EP-20); no source yet
