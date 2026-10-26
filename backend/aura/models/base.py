from datetime import UTC, datetime

from sqlalchemy import String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from aura.core import clock
from aura.core.ids import new_id


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes stored as fixed-width ISO-8601 text (sorts and compares as text)."""

    impl = String(27)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> str | None:  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime given to UTCDateTime")
        return clock.iso(value)

    def process_result_value(self, value: str | None, dialect) -> datetime | None:  # noqa: ANN001
        if value is None:
            return None
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


class IdMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)


class CreatedMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=clock.now, nullable=False)
