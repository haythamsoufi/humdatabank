# FormItem Migration Helper - Examples for completing the migration

# STEP 1: After running the migration, uncomment these relationships in models.py:

# In FormSection model:
# form_items = relationship('FormItem', backref='form_section', lazy='dynamic', order_by='FormItem.order', cascade="all, delete-orphan")

# In FormTemplate model:
# template_form_items = relationship(
#     "FormItem",
#     primaryjoin="FormTemplate.id == FormItem.template_id",
#     backref="template",
#     lazy="dynamic",
#     cascade="all, delete-orphan"
# )

# In FormData model:
# form_item = relationship('FormItem', backref='data_entries')

# In SubmittedDocument model:
# form_item = relationship('FormItem', backref='submitted_documents')

# In RepeatGroupData model:
# form_item = db.relationship('FormItem', backref='repeat_data_entries')

# STEP 2: Update route patterns - Examples

# OLD route pattern:
# for indicator in section.indicators:
#     # process indicator

# NEW route pattern:
# for form_item in section.form_items.filter_by(item_type=FormItemType.indicator):
#     # process form_item (it has all the same properties as indicator)

# STEP 3: Update template patterns - Examples

# OLD template pattern:
# {% for field in section.indicators %}
#     {{ field.label }}
# {% endfor %}

# NEW template pattern:
# {% for field in section.form_items.filter(form_item.c.item_type=='indicator') %}
#     {{ field.label }}
# {% endfor %}

# Or create a helper function in the model:
# @property
# def indicators_unified(self):
#     return self.form_items.filter_by(item_type=FormItemType.indicator)

# STEP 4: Update JavaScript patterns - Examples

# OLD JavaScript:
# data-item-type="{{ 'indicator' if hasattr(field, 'indicator_bank_id') else 'question' }}"

# NEW JavaScript:
# data-item-type="{{ field.item_type.value }}"

# STEP 5: Update form processing - Examples

# OLD form processing:
# if form_type == 'indicator':
#     indicator = Indicator.query.get(item_id)
# elif form_type == 'question':
#     question = Question.query.get(item_id)

# NEW form processing:
# form_item = FormItem.query.get(item_id)
# # All properties are available regardless of type
# label = form_item.label
# if form_item.is_indicator:
#     # Handle indicator-specific logic
# elif form_item.is_question:
#     # Handle question-specific logic

# STEP 6: Data creation examples

# OLD data creation:
# form_data = FormData(
#     assignment_country_status_id=status_id,
#     indicator_id=indicator.id if isinstance(field, Indicator) else None,
#     question_id=question.id if isinstance(field, Question) else None,
#     value=value
# )

# NEW data creation:
# form_data = FormData(
#     assignment_country_status_id=status_id,
#     form_item_id=form_item.item_id,
#     value=value
# )

# STEP 7: Query patterns

# OLD queries:
# indicators = Indicator.query.filter_by(section_id=section_id).all()
# questions = Question.query.filter_by(section_id=section_id).all()
# documents = DocumentField.query.filter_by(section_id=section_id).all()

# NEW queries:
# indicators = FormItem.query.filter_by(section_id=section_id, item_type=FormItemType.indicator).all()
# questions = FormItem.query.filter_by(section_id=section_id, item_type=FormItemType.question).all()
# documents = FormItem.query.filter_by(section_id=section_id, item_type=FormItemType.document_field).all()

# Or get all together:
# all_items = FormItem.query.filter_by(section_id=section_id).order_by(FormItem.order).all()

# STEP 8: Create helper properties in FormSection for easier migration

# Add these to FormSection model:
# @property
# def all_form_items_ordered(self):
#     return self.form_items.order_by(FormItem.order).all()
#
# @property
# def indicators_unified(self):
#     return self.form_items.filter_by(item_type=FormItemType.indicator).order_by(FormItem.order)
#
# @property
# def questions_unified(self):
#     return self.form_items.filter_by(item_type=FormItemType.question).order_by(FormItem.order)
#
# @property
# def document_fields_unified(self):
#     return self.form_items.filter_by(item_type=FormItemType.document_field).order_by(FormItem.order)

# STEP 9: Template helper example for existing templates

# Add this to template context or as a Jinja filter:
# def get_unified_fields(section):
#     """Returns all form items in a section, maintaining backward compatibility"""
#     items = []
#     # Add indicators
#     for item in section.form_items.filter_by(item_type=FormItemType.indicator):
#         items.append(item)
#     # Add questions
#     for item in section.form_items.filter_by(item_type=FormItemType.question):
#         items.append(item)
#     # Add document fields
#     for item in section.form_items.filter_by(item_type=FormItemType.document_field):
#         items.append(item)
#     return sorted(items, key=lambda x: x.order)
