from enum import Enum

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, DateField, widgets
from wtforms.validators import DataRequired, Optional, Length


class ResourceType(Enum):
    TECH = 1
    INFO = 2
    PAY = 3
    FMC = 4


class ResourceForm(FlaskForm):
    name = StringField(
        validators=[DataRequired(), Length(min=1, max=30)],
        render_kw={'class': 'form-control'},
    )

    resource_type = SelectField(
        choices=[r.name for r in ResourceType],
        validators=[DataRequired()],
        render_kw={'class': 'form-select'},
    )

    order = StringField(render_kw={'class': 'form-control'})
    added_date = DateField(
        validators=[Optional()],
        render_kw={'class': 'form-control', 'placeholder': 'yyyy-mm-dd'},
        widget=widgets.TextInput(),
        format='%Y-%m-%d')
    resolve_time = DateField(render_kw={'class': 'form-control'})
    description = StringField(
        validators=[Length(min=0, max=200)],
        render_kw={'class': 'form-control'}
    )
