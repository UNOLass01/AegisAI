"""Re-export ORM models so Alembic's target_metadata sees every table."""
from app.models.base import Base  # noqa: F401
from app.models.investigation import Investigation  # noqa: F401

__all__ = ["Base", "Investigation"]
