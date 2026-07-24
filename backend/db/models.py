"""SQLAlchemy ORM modelleri.

business_types, businesses ve appointment_slots tabloları — şema
tasarımı ve kararların gerekçesi için bkz. docs/database_schema.md.
"""

from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Tüm modellerin ortak temel sınıfı."""


class BusinessType(Base):
    """İşletme kategorileri (referans tablo, 27 sabit satır)."""

    __tablename__ = "business_types"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    category_group: Mapped[str] = mapped_column(String(50), nullable=False)

    businesses: Mapped[list["Business"]] = relationship(back_populates="business_type")


class Business(Base):
    """İşletme kaydı."""

    __tablename__ = "businesses"
    __table_args__ = (
        Index("ix_businesses_tags_gin", "tags", postgresql_using="gin"),
        Index("ix_businesses_keywords_gin", "keywords", postgresql_using="gin"),
        Index("ix_businesses_search_vector_gin", "search_vector", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    place_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    type_normalized: Mapped[str] = mapped_column(
        ForeignKey("business_types.name"), nullable=False, index=True
    )

    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    weighted_rating: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    reviews: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    price_min: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    price_max: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    appointment_duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    online_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    gender: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    services: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)

    working_hours: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    rich_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    business_type: Mapped[BusinessType] = relationship(back_populates="businesses")
    slots: Mapped[list["AppointmentSlot"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )


class AppointmentSlot(Base):
    """Bir işletmenin randevu slotu."""

    __tablename__ = "appointment_slots"
    __table_args__ = (
        Index("ix_slots_business_start_booked", "business_id", "start_time", "is_booked"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_booked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    business: Mapped[Business] = relationship(back_populates="slots")
