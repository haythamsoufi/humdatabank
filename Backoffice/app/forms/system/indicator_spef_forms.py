# Central indicator SP/EF (SPEF) catalog (admin)
import re

from wtforms import BooleanField, IntegerField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.extensions import db
from app.models import IndicatorBankSpef

from ..base import BaseForm, MultilingualFieldsMixin

_SPEF_CODE_RE = re.compile(r"^[A-Za-z]{2}\d{1,2}$")


def _normalize_spef_code(code: str) -> str:
    c = (code or "").strip().upper()
    if not _SPEF_CODE_RE.match(c):
        raise ValidationError(
            "Code must match SP/EF format (e.g. EF2, SP3): two letters followed by 1–2 digits."
        )
    return c


class IndicatorBankSpefForm(BaseForm, MultilingualFieldsMixin):
    code = StringField(
        "Code",
        validators=[DataRequired(), Length(max=16)],
        render_kw={"placeholder": "e.g. EF2, SP3"},
    )
    name = StringField("English label", validators=[DataRequired(), Length(max=200)])
    sort_order = IntegerField("Display order", default=0, validators=[Optional()])
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save")

    def __init__(self, *args, editing_id=None, **kwargs):
        self._editing_id = editing_id
        self.add_multilingual_name_fields("name", max_length=200)
        super().__init__(*args, **kwargs)
        if self.sort_order.data is None:
            self.sort_order.data = 0

    def validate_code(self, field):
        _normalize_spef_code(field.data or "")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        code = _normalize_spef_code(self.code.data or "")
        q = IndicatorBankSpef.query.filter(db.func.upper(IndicatorBankSpef.code) == code)
        if self._editing_id:
            q = q.filter(IndicatorBankSpef.id != self._editing_id)
        if q.first():
            self.code.errors.append("This code is already in use.")
            return False
        return True
