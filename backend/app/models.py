from datetime import datetime, timezone

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(64), default="旅行者")
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_uid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    provider_uid: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Region(Base):
    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(16))  # world | country | macro | province | city
    name: Mapped[str] = mapped_column(String(64))
    name_en: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)  # WGS-84, always
    path: Mapped[str] = mapped_column(String(255), default="")  # materialized path "/1/3/17"


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    uploader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    file_key: Mapped[str] = mapped_column(String(255))
    lat: Mapped[float] = mapped_column(Float)  # WGS-84 truth, never sent to client before guess
    lng: Mapped[float] = mapped_column(Float)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    story: Mapped[str] = mapped_column(Text, default="")
    lang: Mapped[str] = mapped_column(String(8), default="zh-CN")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending | live | rejected
    reject_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    difficulty: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Hint(Base):
    __tablename__ = "hints"
    __table_args__ = (UniqueConstraint("photo_id", "level"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id"), index=True)
    level: Mapped[int] = mapped_column(Integer)  # 1 story teaser | 2 ai clue | 3 macro region | 4 province
    content: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(16))  # uploader | ai | system


class AIGuess(Base):
    __tablename__ = "ai_guesses"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id"), unique=True, index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    distance_km: Mapped[float] = mapped_column(Float)
    score: Mapped[int] = mapped_column(Integer)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(64), default="fake-ai-v0")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    region_id: Mapped[int | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="playing")  # playing | finished
    total_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id"))
    order_index: Mapped[int] = mapped_column(Integer)
    hints_mask: Mapped[int] = mapped_column(Integer, default=0)  # bit N-1 = hint level N used
    guess_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    guess_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)


class PointsLedger(Base):
    __tablename__ = "points_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    delta: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))  # photo_played | photo_guessed_close | ...
    ref_type: Mapped[str] = mapped_column(String(16), default="")
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    content: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photos.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content: Mapped[str] = mapped_column(String(1000))
    contact: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Event(Base):
    """通用埋点:event_type+meta(JSON字符串) 而不是每种事件建一张表,以后加新事件类型不用改表结构。"""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    ref_type: Mapped[str] = mapped_column(String(16), default="")
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
