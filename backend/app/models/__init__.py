"""Database models. Structure: User → Agency → (Members, Clients → Projects → Social Accounts → Posts / Metrics)."""
import time
import uuid

from sqlalchemy import JSON, BigInteger, Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def new_id() -> str:
    return uuid.uuid4().hex


def now_ms() -> int:
    return int(time.time() * 1000)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[int] = mapped_column(BigInteger)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class Agency(Base):
    __tablename__ = "agencies"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(255))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    plan: Mapped[str] = mapped_column(String(20), default="pro")  # free | starter | pro | agency
    plan_renews_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    report_footer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hide_social_grow_branding: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # SaaS lifecycle (null status/subscription = legacy, treated as active)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # pending|active|rejected|suspended
    subscription_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # trialing|active|expired
    trial_ends_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    current_period_end: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approved_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    billing_cycle: Mapped[str | None] = mapped_column(String(10), nullable=True)  # monthly|yearly
    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    razorpay_sub_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pending_plan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cancel_at_period_end: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class Member(Base):
    __tablename__ = "members"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20))  # owner|admin|manager|analyst|content_manager|viewer
    status: Mapped[str] = mapped_column(String(10), default="active")  # active|invited
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    platforms: Mapped[list] = mapped_column(JSON, default=list)
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(12), default="active")
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(12))  # instagram|facebook|youtube
    username: Mapped[str] = mapped_column(String(255))
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mode: Mapped[str] = mapped_column(String(8), default="demo")  # demo|api
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    followers: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_total_views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_synced_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sync_error: Mapped[str | None] = mapped_column(String(400), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="connected")  # connected|needs_reconnect|disconnected
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class MetricDaily(Base):
    __tablename__ = "metrics_daily"
    __table_args__ = (Index("ix_metrics_account_date", "account_id", "date"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("social_accounts.id", ondelete="CASCADE"))
    date: Mapped[str] = mapped_column(String(10))
    followers: Mapped[int] = mapped_column(BigInteger, default=0)
    following: Mapped[int] = mapped_column(BigInteger, default=0)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comments: Mapped[int] = mapped_column(BigInteger, default=0)
    shares: Mapped[int] = mapped_column(BigInteger, default=0)
    posts_count: Mapped[int] = mapped_column(Integer, default=0)


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_agency_date", "agency_id", "published_at"),
        Index("ix_posts_account_external", "account_id", "external_id"),
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"))
    account_id: Mapped[str] = mapped_column(ForeignKey("social_accounts.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(12))
    format: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(300))
    published_at: Mapped[str] = mapped_column(String(10))
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    views: Mapped[int] = mapped_column(BigInteger, default=0)
    likes: Mapped[int] = mapped_column(BigInteger, default=0)
    comments: Mapped[int] = mapped_column(BigInteger, default=0)
    shares: Mapped[int] = mapped_column(BigInteger, default=0)


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("social_accounts.id", ondelete="CASCADE"))
    start_value: Mapped[int] = mapped_column(BigInteger)
    target: Mapped[int] = mapped_column(BigInteger)
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    platform: Mapped[str] = mapped_column(String(12))
    goal: Mapped[str] = mapped_column(String(64))
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    budget: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(12), default="planned")
    content_planned: Mapped[int] = mapped_column(Integer, default=0)
    content_published: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class ContentItem(Base):
    __tablename__ = "content_items"
    __table_args__ = (Index("ix_content_agency_date", "agency_id", "date"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"))
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id", ondelete="SET NULL"), nullable=True)
    date: Mapped[str] = mapped_column(String(10))
    platform: Mapped[str] = mapped_column(String(12))
    format: Mapped[str] = mapped_column(String(32))
    topic: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="idea")
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(32))
    period_start: Mapped[str] = mapped_column(String(10))
    period_end: Mapped[str] = mapped_column(String(10))
    data: Mapped[str] = mapped_column(Text)
    ai_summary: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(32))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class AiLog(Base):
    __tablename__ = "ai_logs"
    __table_args__ = (Index("ix_ai_agency_month", "agency_id", "month"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(32))
    month: Mapped[str] = mapped_column(String(7), index=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), index=True)
    plan: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    status: Mapped[str] = mapped_column(String(12), index=True)  # paid|test|pending|rejected
    invoice_no: Mapped[str] = mapped_column(String(40))
    method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class PlatformSettings(Base):
    __tablename__ = "platform_settings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    upi_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trial_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    razorpay_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    razorpay_key_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    razorpay_webhook_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    razorpay_plans: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class Integration(Base):
    __tablename__ = "integrations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    agency_id: Mapped[str] = mapped_column(ForeignKey("agencies.id", ondelete="CASCADE"), unique=True)
    youtube_api_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    meta_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_token_expires_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    meta_app_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ig_business_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ig_username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    meta_pages: Mapped[list | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=now_ms)


class PlatformAdmin(Base):
    __tablename__ = "platform_admins"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
