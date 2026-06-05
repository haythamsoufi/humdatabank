"""Pluggable data quality methodology registry."""

from app.services.data_quality.methodologies.fdrs_v1 import FdrsV1Methodology
from app.utils.data_quality_constants import METHODOLOGY_FDRS_V1

METHODOLOGIES = {
    METHODOLOGY_FDRS_V1: FdrsV1Methodology,
}


def get_methodology(code: str):
    cls = METHODOLOGIES.get(code)
    if cls is None:
        raise ValueError(f"Unknown data quality methodology: {code}")
    return cls()
