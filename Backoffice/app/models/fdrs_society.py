"""FDRS society reference for the public-frontend compatibility API.

The legacy FDRS data API identifies a National Society by a *DON code* (``DKEN001``)
and groups societies into zones ``S1``-``S5``. Neither exists on ``Country`` or
``NationalSociety``, so the public-frontend adapter
(``plugins/fdrs/public_compat_routes.py``) reads them from this table.

One row per society the public site can select. Seed it once from the current
``GET /api/entities/ns`` payload (``flask fdrs-societies import``), then maintain it
here.
"""

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.extensions import db
from app.utils.datetime_helpers import utcnow

FDRS_ZONES = {
    "S1": "Africa",
    "S2": "Americas",
    "S3": "Asia Pacific",
    "S4": "Europe and Central Asia",
    "S5": "Middle East and North Africa",
}


class FdrsSociety(db.Model):
    __tablename__ = "fdrs_society"

    id = Column(Integer, primary_key=True)
    don_code = Column(String(20), nullable=False, unique=True, index=True)
    country_id = Column(
        Integer,
        ForeignKey("country.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name = Column(String(255), nullable=False)
    country_name = Column(String(255), nullable=True)
    iso2 = Column(String(2), nullable=True)
    iso3 = Column(String(3), nullable=True)
    zone_code = Column(String(2), nullable=True, index=True)
    zone_name = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    admission_date = Column(Date, nullable=True)
    admission_date_note = Column(Text, nullable=True)
    currency_code = Column(String(3), nullable=True)
    search_string = Column(Text, nullable=True)
    website = Column(Text, nullable=True)
    facebook = Column(Text, nullable=True)
    twitter = Column(Text, nullable=True)
    other_social = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    country = relationship("Country", lazy="joined")

    def __repr__(self) -> str:
        return f"<FdrsSociety {self.don_code} {self.name!r}>"
