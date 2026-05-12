# Central indicator type / unit catalog (admin)
import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, IntegerField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from app.extensions import db
from app.models import IndicatorBankType, IndicatorBankUnit

from ..base import BaseForm, MultilingualFieldsMixin


_CODE_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _validate_code_pattern(code: str):
    c = (code or "").strip().lower()
    if not _CODE_RE.match(c):
        raise ValidationError(
            "Code must be 1–64 characters: lowercase letters, digits, underscore only."
        )
    return c


class IndicatorBankTypeForm(BaseForm, MultilingualFieldsMixin):
    code = StringField(
        "Code",
        validators=[DataRequired(), Length(max=64)],
        render_kw={"placeholder": "e.g. number"},
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
        _validate_code_pattern(field.data or "")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        code = (self.code.data or "").strip().lower()
        q = IndicatorBankType.query.filter(db.func.lower(IndicatorBankType.code) == code)
        if self._editing_id:
            q = q.filter(IndicatorBankType.id != self._editing_id)
        if q.first():
            self.code.errors.append("This code is already in use.")
            return False
        return True


class IndicatorBankUnitForm(BaseForm, MultilingualFieldsMixin):
    code = StringField(
        "Code",
        validators=[DataRequired(), Length(max=64)],
        render_kw={"placeholder": "e.g. people"},
    )
    name = StringField("English label", validators=[DataRequired(), Length(max=200)])
    sort_order = IntegerField("Display order", default=0, validators=[Optional()])
    is_active = BooleanField("Active", default=True)
    allows_disaggregation = BooleanField("Allows disaggregation (with Number type)", default=False)
    submit = SubmitField("Save")

    def __init__(self, *args, editing_id=None, **kwargs):
        self._editing_id = editing_id
        self.add_multilingual_name_fields("name", max_length=200)
        super().__init__(*args, **kwargs)
        if self.sort_order.data is None:
            self.sort_order.data = 0

    def validate_code(self, field):
        _validate_code_pattern(field.data or "")

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False
        code = (self.code.data or "").strip().lower()
        q = IndicatorBankUnit.query.filter(db.func.lower(IndicatorBankUnit.code) == code)
        if self._editing_id:
            q = q.filter(IndicatorBankUnit.id != self._editing_id)
        if q.first():
            self.code.errors.append("This code is already in use.")
            return False
        return True
