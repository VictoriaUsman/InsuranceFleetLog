import enum

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AppStatus(str, enum.Enum):
    OFF = "off"
    ON_AVAILABLE = "on_available"
    ON_JOB = "on_job"


class Car(Base):
    __tablename__ = "cars"

    car_id: Mapped[int] = mapped_column(primary_key=True)
    vin: Mapped[str | None] = mapped_column(String, unique=True)
    license_plate: Mapped[str | None] = mapped_column(String)
    gps_device_id: Mapped[str | None] = mapped_column(String, unique=True)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Renter(Base):
    __tablename__ = "renters"

    renter_id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    argyle_user_id: Mapped[str | None] = mapped_column(String, unique=True)
    ghl_contact_id: Mapped[str | None] = mapped_column(String, unique=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RentalAssignment(Base):
    __tablename__ = "rental_assignments"

    assignment_id: Mapped[int] = mapped_column(primary_key=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.car_id"), nullable=False)
    renter_id: Mapped[int] = mapped_column(ForeignKey("renters.renter_id"), nullable=False)
    start_date: Mapped[object] = mapped_column(Date, nullable=False)
    end_date: Mapped[object | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String, default="gohighlevel")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

    car: Mapped["Car"] = relationship()
    renter: Mapped["Renter"] = relationship()


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (UniqueConstraint("car_id", "start_time_utc", "end_time_utc"),)

    trip_id: Mapped[int] = mapped_column(primary_key=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.car_id"), nullable=False)
    start_time_utc: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time_utc: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    miles: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

    car: Mapped["Car"] = relationship()


class AppStatusInterval(Base):
    __tablename__ = "app_status_intervals"

    interval_id: Mapped[int] = mapped_column(primary_key=True)
    renter_id: Mapped[int] = mapped_column(ForeignKey("renters.renter_id"), nullable=False)
    start_time_utc: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time_utc: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AppStatus] = mapped_column(Enum(AppStatus, name="app_status"), nullable=False)
    source: Mapped[str] = mapped_column(String, default="argyle")
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())

    renter: Mapped["Renter"] = relationship()


class MonthlyReport(Base):
    __tablename__ = "monthly_reports"
    __table_args__ = (UniqueConstraint("car_id", "report_month"),)

    report_id: Mapped[int] = mapped_column(primary_key=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.car_id"), nullable=False)
    report_month: Mapped[object] = mapped_column(Date, nullable=False)
    p0_miles: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    p1_miles: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    p2_miles: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    total_miles: Mapped[float] = mapped_column(Numeric(9, 2), nullable=False)
    generated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
