"""Declarative base for ORM models (MASTER_PLAN Task 2.5).

Models mirror the LOCKED schema in Section 10. They are NOT used to create the
schema (Alembic owns DDL, including partitioning); they exist for typed querying
and CRUD via the repositories.
"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""
