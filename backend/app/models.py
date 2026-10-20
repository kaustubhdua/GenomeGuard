"""SQLAlchemy tables (section 6).

Genotypes are deliberately NOT a column on `donors`: they live in a separate table as a compressed
numpy blob and no API route ever selects from it.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Donor(Base):
    __tablename__ = "donors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cohort_id: Mapped[str] = mapped_column(String(32), index=True)
    population: Mapped[str] = mapped_column(String(32), index=True)
    consent_json: Mapped[dict] = mapped_column(JSON)
    family_id: Mapped[int] = mapped_column(Integer, index=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Genotype(Base):
    """Per-donor genotype vector (0/1/2 minor-allele counts) as compressed numpy bytes."""

    __tablename__ = "genotypes"
    donor_id: Mapped[int] = mapped_column(ForeignKey("donors.id"), primary_key=True)
    genotype_blob: Mapped[bytes] = mapped_column(LargeBinary)


class Relationship(Base):
    """Pedigree edge, used for the relative-exposure model. relation is from a to b."""

    __tablename__ = "relationships"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donor_a: Mapped[int] = mapped_column(ForeignKey("donors.id"), index=True)
    donor_b: Mapped[int] = mapped_column(ForeignKey("donors.id"), index=True)
    relation: Mapped[str] = mapped_column(String(48))
    meioses: Mapped[int] = mapped_column(Integer)  # genealogical distance (parent=1, sibling=2)
    shared_fraction: Mapped[float] = mapped_column(Float)  # EXPECTED average, real sharing varies


class Variant(Base):
    __tablename__ = "variants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chrom: Mapped[str] = mapped_column(String(4))
    pos: Mapped[int] = mapped_column(Integer)
    ref: Mapped[str] = mapped_column(String(1))
    alt: Mapped[str] = mapped_column(String(1))
    maf: Mapped[float] = mapped_column(Float)
    is_rare: Mapped[bool] = mapped_column(Boolean, default=False)


class Requester(Base):
    __tablename__ = "requesters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(64), default="researcher")
    credential_level: Mapped[str] = mapped_column(String(16), default="registered")
    institution: Mapped[str] = mapped_column(String(128), default="")
    api_key_hash: Mapped[str] = mapped_column(String(64), default="")  # sha256 hex, never plaintext
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Request(Base):
    __tablename__ = "requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("requesters.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    purpose: Mapped[str] = mapped_column(String(64))
    disease: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_commercial: Mapped[bool] = mapped_column(Boolean, default=False)
    data_level: Mapped[str] = mapped_column(String(16), default="frequency")
    cohort_filter_json: Mapped[dict] = mapped_column(JSON, default=dict)
    variant_filter_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")


class Decision(Base):
    __tablename__ = "decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), unique=True)
    outcome: Mapped[str] = mapped_column(String(24))
    reasons_json: Mapped[list] = mapped_column(JSON, default=list)
    risk_json: Mapped[dict] = mapped_column(JSON, default=dict)
    transform_json: Mapped[dict] = mapped_column(JSON, default=dict)
    explanation_text: Mapped[str] = mapped_column(Text, default="")
    needs_human: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EpsilonLedger(Base):
    __tablename__ = "epsilon_ledger"
    requester_id: Mapped[int] = mapped_column(ForeignKey("requesters.id"), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    epsilon_spent: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    idx: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    ts: Mapped[str] = mapped_column(String(40))  # ISO string, stored as-is so hashing is exact
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("requesters.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    kind: Mapped[str] = mapped_column(String(32))
    score: Mapped[float] = mapped_column(Float)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    action_taken: Mapped[str] = mapped_column(String(16), default="ok")
