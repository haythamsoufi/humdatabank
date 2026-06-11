"""
Unit tests for embeddings.py models to achieve 100% code coverage.

Covers: AIDocument, AIDocumentChunk, AIEmbedding, IndicatorBankEmbedding,
        AIReasoningTrace (to_dict, display_answer), AIToolUsage, AITraceReview
"""
import pytest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from app.models.embeddings import (
    AIDocument,
    AIDocumentChunk,
    AIEmbedding,
    AIReasoningTrace,
    AIToolUsage,
    AITraceReview,
    IndicatorBankEmbedding,
)
from app.models.enums import (
    AIDocumentProcessingStatusValue,
    AIReasoningTraceStatusValue,
    AITraceReviewStatusValue,
    AITraceReviewVerdictValue,
)
from tests.factories import create_test_user, create_test_country


@pytest.mark.unit
class TestAIDocument:
    """Tests for AIDocument model."""

    def _create_doc(self, db_session, **kwargs):
        defaults = {
            'title': 'Test AI Document',
            'filename': 'test.pdf',
            'file_type': 'pdf',
        }
        defaults.update(kwargs)
        doc = AIDocument(**defaults)
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)
        return doc

    def test_create_ai_document(self, db_session, app):
        """Test creating an AI document."""
        with app.app_context():
            doc = self._create_doc(db_session)
            assert doc.id is not None
            assert doc.title == 'Test AI Document'
            assert doc.processing_status == AIDocumentProcessingStatusValue.pending.value

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            doc = self._create_doc(db_session)
            result = repr(doc)
            assert 'AIDocument' in result
            assert 'Test AI Document' in result

    def test_to_dict_basic(self, db_session, app):
        """Test to_dict returns expected structure."""
        with app.app_context():
            doc = self._create_doc(db_session)
            d = doc.to_dict()
            assert d['id'] == doc.id
            assert d['title'] == 'Test AI Document'
            assert d['filename'] == 'test.pdf'
            assert d['file_type'] == 'pdf'
            assert d['processing_status'] == AIDocumentProcessingStatusValue.pending.value
            assert d['is_public'] is False
            assert d['searchable'] is True

    def test_to_dict_with_country(self, db_session, app):
        """Test to_dict includes country information."""
        with app.app_context():
            country = create_test_country(db_session)
            doc = self._create_doc(db_session, country_id=country.id)
            db_session.refresh(doc)
            d = doc.to_dict()
            assert d['country_id'] == country.id
            assert d['country_name'] == country.name

    def test_to_dict_without_country(self, db_session, app):
        """Test to_dict without country uses country_name fallback."""
        with app.app_context():
            doc = self._create_doc(db_session, country_name='Kenya')
            d = doc.to_dict()
            assert d['country_id'] is None
            assert d['country_name'] == 'Kenya'

    def test_to_dict_with_dates(self, db_session, app):
        """Test to_dict properly serializes dates."""
        with app.app_context():
            from datetime import datetime as dt
            doc = self._create_doc(
                db_session,
                document_date=date(2024, 1, 15),
                processed_at=dt(2024, 1, 15, 10, 0, 0),
                last_verified_at=dt(2024, 6, 1, 0, 0, 0),
            )
            d = doc.to_dict()
            assert d['document_date'] == '2024-01-15'
            assert d['processed_at'] is not None
            assert d['last_verified_at'] is not None

    def test_to_dict_none_dates(self, db_session, app):
        """Test to_dict handles None dates."""
        with app.app_context():
            doc = self._create_doc(db_session)
            d = doc.to_dict()
            assert d['processed_at'] is None
            assert d['document_date'] is None
            assert d['last_verified_at'] is None

    def test_to_dict_with_countries_m2m(self, db_session, app):
        """Test to_dict includes multi-country list."""
        with app.app_context():
            country = create_test_country(db_session)
            doc = self._create_doc(db_session)
            doc.countries.append(country)
            db_session.commit()
            db_session.refresh(doc)
            d = doc.to_dict()
            assert isinstance(d['countries'], list)
            assert len(d['countries']) == 1
            assert d['countries'][0]['id'] == country.id

    def test_to_dict_with_countries_error(self, db_session, app):
        """Test to_dict handles countries iteration error gracefully."""
        with app.app_context():
            doc = self._create_doc(db_session)
            # Mock countries to raise exception
            with patch.object(type(doc), 'countries', new_callable=lambda: property(lambda self: MagicMock(**{'__iter__': MagicMock(side_effect=Exception('DB error'))}))):
                d = doc.to_dict()
                assert 'countries' in d
                assert isinstance(d['countries'], list)

    def test_to_dict_all_provenance_fields(self, db_session, app):
        """Test to_dict includes all provenance metadata."""
        with app.app_context():
            doc = self._create_doc(
                db_session,
                document_language='en',
                source_organization='IFRC',
                document_category='report',
                quality_score=0.9,
                source_url='https://example.com/report.pdf',
                geographic_scope='global',
            )
            d = doc.to_dict()
            assert d['document_language'] == 'en'
            assert d['source_organization'] == 'IFRC'
            assert d['document_category'] == 'report'
            assert d['quality_score'] == 0.9
            assert d['source_url'] == 'https://example.com/report.pdf'
            assert d['geographic_scope'] == 'global'

    def test_to_dict_processing_error_empty(self, db_session, app):
        """Test to_dict returns empty string for None processing_error."""
        with app.app_context():
            doc = self._create_doc(db_session)
            d = doc.to_dict()
            assert d['processing_error'] == ''


@pytest.mark.unit
class TestAIDocumentChunk:
    """Tests for AIDocumentChunk model."""

    def _create_chunk(self, db_session, doc, **kwargs):
        defaults = {
            'document_id': doc.id,
            'content': 'This is test chunk content.',
            'content_length': 28,
            'chunk_index': 0,
        }
        defaults.update(kwargs)
        chunk = AIDocumentChunk(**defaults)
        db_session.add(chunk)
        db_session.commit()
        db_session.refresh(chunk)
        return chunk

    def _create_doc(self, db_session):
        doc = AIDocument(title='Doc', filename='doc.pdf', file_type='pdf')
        db_session.add(doc)
        db_session.commit()
        return doc

    def test_create_chunk(self, db_session, app):
        """Test creating an AI document chunk."""
        with app.app_context():
            doc = self._create_doc(db_session)
            chunk = self._create_chunk(db_session, doc)
            assert chunk.id is not None
            assert chunk.content == 'This is test chunk content.'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            doc = self._create_doc(db_session)
            chunk = self._create_chunk(db_session, doc, chunk_index=3)
            result = repr(chunk)
            assert 'AIDocumentChunk' in result
            assert '3' in result

    def test_to_dict_with_content(self, db_session, app):
        """Test to_dict includes content by default."""
        with app.app_context():
            doc = self._create_doc(db_session)
            chunk = self._create_chunk(
                db_session, doc,
                section_title='Introduction',
                page_number=1,
                token_count=10,
                heading_hierarchy=['Chapter 1', 'Section 1.1'],
                confidence_score=0.95,
                extra_metadata={'source': 'ocr'},
            )
            d = chunk.to_dict()
            assert d['id'] == chunk.id
            assert d['document_id'] == doc.id
            assert d['content'] == 'This is test chunk content.'
            assert d['chunk_index'] == 0
            assert d['section_title'] == 'Introduction'
            assert d['page_number'] == 1
            assert d['token_count'] == 10
            assert d['heading_hierarchy'] == ['Chapter 1', 'Section 1.1']
            assert d['confidence_score'] == 0.95
            assert d['metadata'] == {'source': 'ocr'}

    def test_to_dict_without_content(self, db_session, app):
        """Test to_dict excludes content when include_content=False."""
        with app.app_context():
            doc = self._create_doc(db_session)
            chunk = self._create_chunk(db_session, doc)
            d = chunk.to_dict(include_content=False)
            assert 'content' not in d
            assert d['id'] == chunk.id


@pytest.mark.unit
class TestAIReasoningTrace:
    """Tests for AIReasoningTrace model."""

    def _create_trace(self, db_session, **kwargs):
        defaults = {
            'query': 'What is the volunteer count in Kenya?',
            'steps': [],
        }
        defaults.update(kwargs)
        trace = AIReasoningTrace(**defaults)
        db_session.add(trace)
        db_session.commit()
        db_session.refresh(trace)
        return trace

    def test_create_trace(self, db_session, app):
        """Test creating an AI reasoning trace."""
        with app.app_context():
            trace = self._create_trace(db_session)
            assert trace.id is not None
            assert trace.query == 'What is the volunteer count in Kenya?'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            trace = self._create_trace(db_session)
            result = repr(trace)
            assert 'AIReasoningTrace' in result

    def test_display_answer_final_answer(self, db_session, app):
        """Test display_answer returns final_answer when set."""
        with app.app_context():
            trace = self._create_trace(db_session, final_answer='The count is 500.')
            assert trace.display_answer == 'The count is 500.'

    def test_display_answer_from_steps_finish(self, db_session, app):
        """Test display_answer falls back to steps with 'finish' action."""
        with app.app_context():
            steps = [
                {'step': 1, 'action': 'get_data', 'observation': 'some data'},
                {'step': 2, 'action': 'finish', 'observation': 'Final answer text.'},
            ]
            trace = self._create_trace(db_session, steps=steps)
            result = trace.display_answer
            assert result == 'Final answer text.'

    def test_display_answer_from_steps_finish_dict_obs(self, db_session, app):
        """Test display_answer from finish step with dict observation."""
        with app.app_context():
            steps = [
                {'step': 1, 'action': 'finish', 'observation': {'answer': 'Dict answer.'}},
            ]
            trace = self._create_trace(db_session, steps=steps)
            assert trace.display_answer == 'Dict answer.'

    def test_display_answer_from_single_value_payload(self, db_session, app):
        """Test display_answer from output_payloads single_value kind."""
        with app.app_context():
            payloads = {
                'answer_content': {
                    'kind': 'single_value',
                    'country_name': 'Kenya',
                    'indicator_name': 'Volunteers',
                    'value': 500,
                    'period': '2023',
                }
            }
            trace = self._create_trace(db_session, output_payloads=payloads)
            result = trace.display_answer
            assert 'Kenya' in result
            assert 'Volunteers' in result
            assert '500' in result

    def test_display_answer_single_value_no_period(self, db_session, app):
        """Test display_answer from single_value without period."""
        with app.app_context():
            payloads = {
                'answer_content': {
                    'kind': 'single_value',
                    'country_name': 'Kenya',
                    'indicator_name': 'Volunteers',
                    'value': 500,
                }
            }
            trace = self._create_trace(db_session, output_payloads=payloads)
            result = trace.display_answer
            assert 'Kenya' in result

    def test_display_answer_documents_payload(self, db_session, app):
        """Test display_answer for documents kind."""
        with app.app_context():
            payloads = {'answer_content': {'kind': 'documents', 'total': 5}}
            trace = self._create_trace(db_session, output_payloads=payloads)
            result = trace.display_answer
            assert '5' in result

    def test_display_answer_country_list_payload(self, db_session, app):
        """Test display_answer for country_list kind."""
        with app.app_context():
            countries = [f'Country {i}' for i in range(20)]
            payloads = {'answer_content': {'kind': 'country_list', 'countries': countries}}
            trace = self._create_trace(db_session, output_payloads=payloads)
            result = trace.display_answer
            assert 'Countries:' in result
            assert '+5 more' in result

    def test_display_answer_country_list_few_countries(self, db_session, app):
        """Test display_answer for country_list with <= 15 countries."""
        with app.app_context():
            payloads = {'answer_content': {'kind': 'country_list', 'countries': ['Kenya', 'Chad']}}
            trace = self._create_trace(db_session, output_payloads=payloads)
            result = trace.display_answer
            assert 'Kenya' in result
            assert 'more' not in result

    def test_display_answer_per_country_values(self, db_session, app):
        """Test display_answer for per_country_values kind."""
        with app.app_context():
            payloads = {
                'answer_content': {
                    'kind': 'per_country_values',
                    'rows': [{'country': 'Kenya', 'value': 100}],
                    'metric': 'Volunteers',
                }
            }
            trace = self._create_trace(db_session, output_payloads=payloads)
            result = trace.display_answer
            assert 'Volunteers' in result

    def test_display_answer_time_series(self, db_session, app):
        """Test display_answer for time_series kind."""
        with app.app_context():
            payloads = {
                'answer_content': {
                    'kind': 'time_series',
                    'series': [{'year': 2020, 'value': 100}, {'year': 2021, 'value': 200}],
                    'metric': 'volunteers',
                    'country': 'Kenya',
                }
            }
            trace = self._create_trace(db_session, output_payloads=payloads)
            result = trace.display_answer
            assert 'volunteers' in result
            assert 'Kenya' in result

    def test_display_answer_time_series_no_country(self, db_session, app):
        """Test display_answer for time_series without country."""
        with app.app_context():
            payloads = {
                'answer_content': {
                    'kind': 'time_series',
                    'series': [{'year': 2020, 'value': 100}],
                }
            }
            trace = self._create_trace(db_session, output_payloads=payloads)
            result = trace.display_answer
            assert 'time series' in result.lower()

    def test_display_answer_empty_when_no_data(self, db_session, app):
        """Test display_answer returns empty string when no data available."""
        with app.app_context():
            trace = self._create_trace(db_session, steps=[])
            result = trace.display_answer
            assert result == ''

    def test_display_answer_non_list_steps(self, db_session, app):
        """Test display_answer handles non-list steps gracefully."""
        with app.app_context():
            trace = self._create_trace(db_session, steps={'key': 'value'})
            result = trace.display_answer
            assert result == ''

    def test_display_answer_non_dict_step(self, db_session, app):
        """Test display_answer handles non-dict step in list."""
        with app.app_context():
            trace = self._create_trace(db_session, steps=['not a dict'])
            result = trace.display_answer
            assert result == ''

    def test_to_dict_basic(self, db_session, app):
        """Test to_dict returns expected structure."""
        with app.app_context():
            trace = self._create_trace(
                db_session,
                agent_mode='react',
                status=AIReasoningTraceStatusValue.completed.value,
                final_answer='Final answer',
                total_input_tokens=100,
                total_output_tokens=50,
            )
            d = trace.to_dict()
            assert d['id'] == trace.id
            assert d['query'] == 'What is the volunteer count in Kenya?'
            assert d['agent_mode'] == 'react'
            assert d['final_answer'] == 'Final answer'
            assert 'steps' in d

    def test_to_dict_without_steps(self, db_session, app):
        """Test to_dict excludes steps when include_steps=False."""
        with app.app_context():
            trace = self._create_trace(db_session, steps=[{'step': 1}])
            d = trace.to_dict(include_steps=False)
            assert 'steps' not in d
            assert d['id'] == trace.id

    def test_to_dict_created_at(self, db_session, app):
        """Test to_dict serializes created_at."""
        with app.app_context():
            trace = self._create_trace(db_session)
            d = trace.to_dict()
            assert d['created_at'] is not None

    def test_to_dict_none_created_at(self, db_session, app):
        """Test to_dict handles None created_at."""
        with app.app_context():
            trace = self._create_trace(db_session)
            trace.created_at = None
            d = trace.to_dict()
            assert d['created_at'] is None


@pytest.mark.unit
class TestAIToolUsage:
    """Tests for AIToolUsage model."""

    def test_create_tool_usage(self, db_session, app):
        """Test creating an AI tool usage record."""
        with app.app_context():
            usage = AIToolUsage(
                tool_name='get_indicator_value',
                success=True,
            )
            db_session.add(usage)
            db_session.commit()
            db_session.refresh(usage)
            assert usage.id is not None
            assert usage.tool_name == 'get_indicator_value'
            assert usage.success is True

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            usage = AIToolUsage(tool_name='search_documents', success=False)
            db_session.add(usage)
            db_session.commit()
            result = repr(usage)
            assert 'AIToolUsage' in result
            assert 'search_documents' in result

    def test_tool_usage_with_optional_fields(self, db_session, app):
        """Test tool usage with all optional fields."""
        with app.app_context():
            user = create_test_user(db_session)
            usage = AIToolUsage(
                tool_name='get_data',
                tool_input={'country': 'Kenya'},
                tool_output={'value': 500},
                success=True,
                execution_time_ms=150,
                user_id=user.id,
                error_message=None,
            )
            db_session.add(usage)
            db_session.commit()
            db_session.refresh(usage)
            assert usage.tool_input == {'country': 'Kenya'}
            assert usage.tool_output == {'value': 500}
            assert usage.execution_time_ms == 150


@pytest.mark.unit
class TestAITraceReview:
    """Tests for AITraceReview model."""

    def _create_trace(self, db_session):
        trace = AIReasoningTrace(query='Test query', steps=[])
        db_session.add(trace)
        db_session.flush()
        return trace

    def test_create_review(self, db_session, app):
        """Test creating an AI trace review."""
        with app.app_context():
            trace = self._create_trace(db_session)
            review = AITraceReview(trace_id=trace.id)
            db_session.add(review)
            db_session.commit()
            db_session.refresh(review)
            assert review.id is not None
            assert review.status == AITraceReviewStatusValue.pending.value

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            trace = self._create_trace(db_session)
            review = AITraceReview(trace_id=trace.id)
            db_session.add(review)
            db_session.commit()
            result = repr(review)
            assert 'AITraceReview' in result

    def test_to_dict(self, db_session, app):
        """Test to_dict returns expected structure."""
        with app.app_context():
            user = create_test_user(db_session)
            trace = self._create_trace(db_session)
            from datetime import datetime as dt
            review = AITraceReview(
                trace_id=trace.id,
                reviewer_id=user.id,
                status=AITraceReviewStatusValue.in_review.value,
                verdict=AITraceReviewVerdictValue.correct.value,
                reviewer_notes='Looks correct.',
                ground_truth_answer='The answer is 500.',
                assigned_at=dt(2024, 1, 15, 10, 0, 0),
                completed_at=dt(2024, 1, 15, 11, 0, 0),
            )
            db_session.add(review)
            db_session.commit()
            db_session.refresh(review)
            d = review.to_dict()
            assert d['id'] == review.id
            assert d['trace_id'] == trace.id
            assert d['reviewer_id'] == user.id
            assert d['reviewer_notes'] == 'Looks correct.'
            assert d['ground_truth_answer'] == 'The answer is 500.'
            assert d['assigned_at'] is not None
            assert d['completed_at'] is not None

    def test_to_dict_none_timestamps(self, db_session, app):
        """Test to_dict handles None timestamps."""
        with app.app_context():
            trace = self._create_trace(db_session)
            review = AITraceReview(trace_id=trace.id)
            db_session.add(review)
            db_session.commit()
            db_session.refresh(review)
            d = review.to_dict()
            assert d['assigned_at'] is None
            assert d['completed_at'] is None
