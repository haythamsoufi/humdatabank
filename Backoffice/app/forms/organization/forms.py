"""WTForms for organization admin CRUD."""
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import StringField, TextAreaField, BooleanField, IntegerField, SelectField, DateField
from wtforms.validators import DataRequired, Optional, Length

from app.models.organization import SecretariatRegionalOffice
from app.services.organization.secretariat_regional_office_service import ensure_secretariat_regional_offices
from app.forms.organization.translation_helpers import add_translation_fields

class CountryForm(FlaskForm):
    """Form for creating/editing countries."""
    name = StringField('Country Name', validators=[DataRequired(), Length(max=100)])
    iso3 = StringField('ISO3 Code', validators=[DataRequired(), Length(min=3, max=3)])
    iso2 = StringField('ISO2 Code', validators=[Optional(), Length(min=2, max=2)])
    secretariat_regional_office_id = SelectField('IFRC Region', coerce=int, validators=[DataRequired()])
    status = SelectField('Status', validators=[Optional()], choices=[('Active', 'Active'), ('Inactive', 'Inactive')])
    preferred_language = StringField('Preferred Language', validators=[Optional()])
    currency_code = StringField('Currency Code', validators=[Optional(), Length(max=3)])

    def __init__(self, *args, **kwargs):
        # Add language fields at runtime (requires app context).
        add_translation_fields(self.__class__, 'name', 'Country Name', 100)
        super().__init__(*args, **kwargs)
        ensure_secretariat_regional_offices()
        offices = SecretariatRegionalOffice.query.filter_by(is_active=True).order_by(
            SecretariatRegionalOffice.display_order, SecretariatRegionalOffice.name,
        ).all()
        self.secretariat_regional_office_id.choices = [(o.id, o.name) for o in offices]


class NationalSocietyForm(FlaskForm):
    """Form for creating/editing National Societies."""
    name = StringField('National Society Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    country_id = SelectField('Country', coerce=int, validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)
    display_order = IntegerField('Display Order', validators=[Optional()])
    logo_file = FileField(
        'Logo (PNG, JPG, GIF, WEBP)',
        validators=[Optional(), FileAllowed(['png', 'jpg', 'jpeg', 'gif', 'webp'], 'Images only')],
    )

    def __init__(self, *args, **kwargs):
        add_translation_fields(self.__class__, 'name', 'National Society Name', 255)
        super().__init__(*args, **kwargs)


class NSBranchForm(FlaskForm):
    """Form for creating/editing NS branches."""
    name = StringField('Branch Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Branch Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    country_id = SelectField('Country', coerce=int, validators=[DataRequired()])
    address = TextAreaField('Address', validators=[Optional()])
    city = StringField('City', validators=[Optional(), Length(max=100)])
    postal_code = StringField('Postal Code', validators=[Optional(), Length(max=20)])
    coordinates = StringField('Coordinates (Lat,Long)', validators=[Optional(), Length(max=100)])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    email = StringField('Email', validators=[Optional(), Length(max=255)])
    website = StringField('Website', validators=[Optional(), Length(max=255)])
    is_active = BooleanField('Active', default=True)
    established_date = DateField('Established Date', validators=[Optional()], format='%Y-%m-%d')
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        add_translation_fields(self.__class__, 'name', 'Branch Name', 255)
        super().__init__(*args, **kwargs)


class NSSubBranchForm(FlaskForm):
    """Form for creating/editing NS sub-branches."""
    name = StringField('Sub-branch Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Sub-branch Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    branch_id = SelectField('Parent Branch', coerce=int, validators=[DataRequired()])
    address = TextAreaField('Address', validators=[Optional()])
    city = StringField('City', validators=[Optional(), Length(max=100)])
    postal_code = StringField('Postal Code', validators=[Optional(), Length(max=20)])
    coordinates = StringField('Coordinates (Lat,Long)', validators=[Optional(), Length(max=100)])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    email = StringField('Email', validators=[Optional(), Length(max=255)])
    is_active = BooleanField('Active', default=True)
    established_date = DateField('Established Date', validators=[Optional()], format='%Y-%m-%d')
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        add_translation_fields(self.__class__, 'name', 'Sub-branch Name', 255)
        super().__init__(*args, **kwargs)


class NSLocalUnitForm(FlaskForm):
    """Form for creating/editing NS local units."""
    name = StringField('Local Unit Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Local Unit Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    branch_id = SelectField('Parent Branch', coerce=int, validators=[DataRequired()])
    subbranch_id = SelectField('Parent Sub-branch (Optional)', coerce=int, validators=[Optional()])
    address = TextAreaField('Address', validators=[Optional()])
    city = StringField('City', validators=[Optional(), Length(max=100)])
    postal_code = StringField('Postal Code', validators=[Optional(), Length(max=20)])
    coordinates = StringField('Coordinates (Lat,Long)', validators=[Optional(), Length(max=100)])
    phone = StringField('Phone', validators=[Optional(), Length(max=50)])
    email = StringField('Email', validators=[Optional(), Length(max=255)])
    is_active = BooleanField('Active', default=True)
    established_date = DateField('Established Date', validators=[Optional()], format='%Y-%m-%d')
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        add_translation_fields(self.__class__, 'name', 'Local Unit Name', 255)
        super().__init__(*args, **kwargs)


class SecretariatDivisionForm(FlaskForm):
    """Form for creating/editing Secretariat divisions."""
    name = StringField('Division Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Division Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    is_active = BooleanField('Active', default=True)
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        add_translation_fields(self.__class__, 'name', 'Division Name', 255)
        super().__init__(*args, **kwargs)


class SecretariatDepartmentForm(FlaskForm):
    """Form for creating/editing Secretariat departments."""
    name = StringField('Department Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Department Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    division_id = SelectField('Parent Division', coerce=int, validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        add_translation_fields(self.__class__, 'name', 'Department Name', 255)
        super().__init__(*args, **kwargs)


class SecretariatRegionalOfficeForm(FlaskForm):
    """Form for creating/editing Secretariat regional offices."""
    name = StringField('Regional Office Name', validators=[DataRequired(), Length(max=255)])
    short_name = StringField('Short Name', validators=[Optional(), Length(max=100)])
    code = StringField('Regional Office Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    is_active = BooleanField('Active', default=True)
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        add_translation_fields(self.__class__, 'name', 'Regional Office Name', 255)
        add_translation_fields(self.__class__, 'short_name', 'Short Name', 100)
        super().__init__(*args, **kwargs)


class SecretariatClusterOfficeForm(FlaskForm):
    """Form for creating/editing Secretariat cluster offices."""
    name = StringField('Cluster Office Name', validators=[DataRequired(), Length(max=255)])
    code = StringField('Cluster Office Code', validators=[Optional(), Length(max=50)])
    description = TextAreaField('Description', validators=[Optional()])
    regional_office_id = SelectField('Parent Regional Office', coerce=int, validators=[DataRequired()])
    is_active = BooleanField('Active', default=True)
    display_order = IntegerField('Display Order', validators=[Optional()])

    def __init__(self, *args, **kwargs):
        add_translation_fields(self.__class__, 'name', 'Cluster Office Name', 255)
        super().__init__(*args, **kwargs)
