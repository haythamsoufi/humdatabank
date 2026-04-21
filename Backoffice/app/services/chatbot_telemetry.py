# ========== Chatbot Telemetry Service ==========
from app.utils.datetime_helpers import utcnow
"""
Comprehensive telemetry tracking for chatbot LLM usage, costs, and performance.

This service tracks:
- API usage (requests, tokens, costs)
- Performance metrics (response times, success rates)
- User interaction patterns
- Function calling statistics
- Error rates and types
"""

import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from threading import Lock
from flask import current_app
from flask_login import current_user
from app.extensions import db
from sqlalchemy import text
from contextlib import suppress

logger = logging.getLogger(__name__)


@dataclass
class ChatbotMetrics:
    """Data class for chatbot interaction metrics"""
    user_id: int
    session_id: str
    timestamp: datetime

    # Request details
    message_length: int
    language: str
    page_context: Optional[str]

    # LLM details
    llm_provider: str  # openai
    model_name: Optional[str]
    function_calls_made: List[str]

    # Performance
    response_time_ms: float
    success: bool
    error_type: Optional[str]

    # Usage (estimated)
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    estimated_cost_usd: Optional[float]

    # Response quality
    response_length: int
    used_provenance: bool


class ChatbotTelemetryService:
    """Service for tracking and analyzing chatbot telemetry"""

    def __init__(self):
        self.metrics_buffer = []
        self.buffer_size = 100  # Batch write to reduce DB load
        self._lock = Lock()

    def track_interaction(self, metrics: ChatbotMetrics):
        """Track a single chatbot interaction"""
        try:
            with self._lock:
                self.metrics_buffer.append(metrics)
                should_flush = len(self.metrics_buffer) >= self.buffer_size

            if should_flush:
                self._flush_metrics()

        except Exception as e:
            logger.error(f"Error tracking chatbot interaction: {e}")

    def _flush_metrics(self):
        """Flush metrics buffer to database"""
        with self._lock:
            if not self.metrics_buffer:
                return
            metrics_batch = self.metrics_buffer
            self.metrics_buffer = []

        try:
            # Create table if not exists
            self._ensure_telemetry_table()

            # Batch insert metrics
            insert_sql = """
            INSERT INTO chatbot_telemetry (
                user_id, session_id, timestamp, message_length, language, page_context,
                llm_provider, model_name, function_calls_made, response_time_ms, success,
                error_type, input_tokens, output_tokens, estimated_cost_usd, response_length,
                used_provenance
            ) VALUES (
                :user_id, :session_id, :timestamp, :message_length, :language, :page_context,
                :llm_provider, :model_name, :function_calls_made, :response_time_ms, :success,
                :error_type, :input_tokens, :output_tokens, :estimated_cost_usd, :response_length,
                :used_provenance
            )
            """

            # Convert metrics to dict format
            metrics_data = []
            for metric in metrics_batch:
                data = asdict(metric)
                data['function_calls_made'] = json.dumps(data['function_calls_made'])
                metrics_data.append(data)

            # Execute batch insert
            db.session.execute(text(insert_sql), metrics_data)
            db.session.commit()

            logger.info(f"Flushed {len(metrics_batch)} chatbot metrics to database")

        except Exception as e:
            logger.error(f"Error flushing chatbot metrics: {e}", exc_info=True)
            try:
                db.session.rollback()
            except Exception as e_rb:
                logger.warning("Chatbot telemetry rollback failed: %s", e_rb, exc_info=True)
            # Re-queue the metrics for a later attempt
            with self._lock:
                self.metrics_buffer = metrics_batch + self.metrics_buffer

    def _ensure_telemetry_table(self):
        """Ensure telemetry table exists"""
        # NOTE: This module is used in dev environments that may run SQLite.
        # Avoid Postgres-only types (e.g. SERIAL) so we don't crash at runtime.
        dialect = None
        try:
            dialect = getattr(getattr(db, "engine", None), "dialect", None)
            dialect = getattr(dialect, "name", None)
        except Exception as e:
            logger.debug("Could not get DB dialect: %s", e)
            dialect = None
        dialect = (dialect or "").lower()

        if dialect == "sqlite":
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS chatbot_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id VARCHAR(255),
                timestamp DATETIME NOT NULL,
                message_length INTEGER,
                language VARCHAR(50),
                page_context TEXT,
                llm_provider VARCHAR(50),
                model_name VARCHAR(100),
                function_calls_made TEXT,
                response_time_ms FLOAT,
                success BOOLEAN,
                error_type VARCHAR(255),
                input_tokens INTEGER,
                output_tokens INTEGER,
                estimated_cost_usd FLOAT,
                response_length INTEGER,
                used_provenance BOOLEAN,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        else:
            # Default: Postgres-compatible (also works for many other DBs).
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS chatbot_telemetry (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                session_id VARCHAR(255),
                timestamp TIMESTAMP NOT NULL,
                message_length INTEGER,
                language VARCHAR(50),
                page_context TEXT,
                llm_provider VARCHAR(50),
                model_name VARCHAR(100),
                function_calls_made TEXT,
                response_time_ms FLOAT,
                success BOOLEAN,
                error_type VARCHAR(255),
                input_tokens INTEGER,
                output_tokens INTEGER,
                estimated_cost_usd FLOAT,
                response_length INTEGER,
                used_provenance BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """

        # Create index for common queries
        create_index_sql = """
        CREATE INDEX IF NOT EXISTS idx_chatbot_telemetry_user_timestamp
        ON chatbot_telemetry (user_id, timestamp DESC)
        """

        try:
            db.session.execute(text(create_table_sql))
            db.session.execute(text(create_index_sql))
            db.session.commit()
        except Exception as e:
            logger.error(f"Error creating telemetry table: {e}", exc_info=True)
            try:
                db.session.rollback()
            except Exception as e_rb:
                logger.warning("Chatbot telemetry rollback failed during table init: %s", e_rb, exc_info=True)

    def get_usage_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get usage statistics for the last N days"""
        try:
            since_date = utcnow() - timedelta(days=days)

            stats_sql = """
            SELECT
                COUNT(*) as total_interactions,
                COUNT(DISTINCT user_id) as unique_users,
                AVG(response_time_ms) as avg_response_time,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_interactions,
                SUM(CASE WHEN llm_provider = 'openai' THEN 1 ELSE 0 END) as openai_usage,
                SUM(CASE WHEN llm_provider != 'openai' THEN 1 ELSE 0 END) as other_usage,
                SUM(estimated_cost_usd) as total_estimated_cost,
                AVG(message_length) as avg_message_length,
                AVG(response_length) as avg_response_length,
                COUNT(CASE WHEN function_calls_made != '[]' THEN 1 END) as function_calls_total
            FROM chatbot_telemetry
            WHERE timestamp >= :since_date
            """

            result = db.session.execute(text(stats_sql), {'since_date': since_date}).fetchone()

            if result:
                stats = dict(result._mapping)

                # Calculate success rate
                total = stats['total_interactions'] or 1
                stats['success_rate'] = (stats['successful_interactions'] / total) * 100

                # Calculate provider distribution
                stats['provider_distribution'] = {
                    'openai': stats.get('openai_usage', 0),
                    'other': stats.get('other_usage', 0),
                }

                return stats

            return {}

        except Exception as e:
            logger.error(f"Error getting usage stats: {e}")
            return {}

    def get_error_analysis(self, days: int = 7) -> Dict[str, Any]:
        """Get error analysis for the last N days"""
        try:
            since_date = utcnow() - timedelta(days=days)

            error_sql = """
            SELECT
                error_type,
                COUNT(*) as error_count,
                AVG(response_time_ms) as avg_response_time
            FROM chatbot_telemetry
            WHERE timestamp >= :since_date AND success = FALSE
            GROUP BY error_type
            ORDER BY error_count DESC
            """

            results = db.session.execute(text(error_sql), {'since_date': since_date}).fetchall()

            errors = []
            for row in results:
                errors.append({
                    'error_type': row.error_type,
                    'count': row.error_count,
                    'avg_response_time': row.avg_response_time
                })

            return {'errors': errors}

        except Exception as e:
            logger.error(f"Error getting error analysis: {e}")
            return {'errors': []}

    def get_function_usage_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get function calling usage statistics"""
        try:
            since_date = utcnow() - timedelta(days=days)

            # Get all function calls data
            function_sql = """
            SELECT function_calls_made
            FROM chatbot_telemetry
            WHERE timestamp >= :since_date AND function_calls_made != '[]'
            """

            results = db.session.execute(text(function_sql), {'since_date': since_date}).fetchall()

            function_counts = {}
            total_function_calls = 0

            for row in results:
                try:
                    functions = json.loads(row.function_calls_made)
                    for func in functions:
                        function_counts[func] = function_counts.get(func, 0) + 1
                        total_function_calls += 1
                except json.JSONDecodeError:
                    continue

            return {
                'total_function_calls': total_function_calls,
                'function_distribution': function_counts,
                'most_used_function': max(function_counts.items(), key=lambda x: x[1])[0] if function_counts else None
            }

        except Exception as e:
            logger.error(f"Error getting function usage stats: {e}")
            return {}

    def estimate_token_usage(self, text: str, is_input: bool = True) -> int:
        """Estimate token usage for text (rough approximation)"""
        # Rough estimation: ~4 characters per token for English
        # This is a simplified estimation - real token counting would require the actual tokenizer
        return max(1, len(text) // 4)

    def estimate_cost(
        self,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        model: Optional[str] = None,
    ) -> float:
        """Estimate cost from centralized pricing (config or defaults)."""
        if provider != "openai":
            return 0.0
        try:
            from flask import current_app
            from app.utils.ai_pricing import estimate_chat_cost
            model_name = model or current_app.config.get("OPENAI_MODEL", "gpt-5-mini")
            return estimate_chat_cost(model_name, input_tokens, output_tokens)
        except Exception:
            return 0.0


# Global telemetry service instance
telemetry_service = ChatbotTelemetryService()


def track_chatbot_interaction(
    message: str,
    response: str,
    llm_provider: str,
    model_name: Optional[str],
    response_time_ms: float,
    success: bool,
    error_type: Optional[str] = None,
    function_calls: Optional[List[str]] = None,
    page_context: Optional[str] = None,
    language: str = 'en',
    used_provenance: bool = False
):
    """
    Convenience function to track a chatbot interaction
    """
    try:
        # Estimate token usage
        input_tokens = telemetry_service.estimate_token_usage(message, is_input=True)
        output_tokens = telemetry_service.estimate_token_usage(response, is_input=False)

        # Estimate cost
        estimated_cost = telemetry_service.estimate_cost(llm_provider, input_tokens, output_tokens)

        # Create metrics object
        metrics = ChatbotMetrics(
            user_id=current_user.id if current_user.is_authenticated else 0,
            session_id=getattr(current_user, 'session_id', 'anonymous'),
            timestamp=utcnow(),
            message_length=len(message),
            language=language,
            page_context=page_context,
            llm_provider=llm_provider,
            model_name=model_name,
            function_calls_made=function_calls or [],
            response_time_ms=response_time_ms,
            success=success,
            error_type=error_type,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost,
            response_length=len(response),
            used_provenance=used_provenance
        )

        # Track the interaction
        telemetry_service.track_interaction(metrics)

    except Exception as e:
        logger.error(f"Error tracking chatbot interaction: {e}")


def get_chatbot_analytics() -> Dict[str, Any]:
    """
    Get comprehensive chatbot analytics
    """
    try:
        usage_stats = telemetry_service.get_usage_stats(days=7)
        error_analysis = telemetry_service.get_error_analysis(days=7)
        function_stats = telemetry_service.get_function_usage_stats(days=7)

        return {
            'usage_stats': usage_stats,
            'error_analysis': error_analysis,
            'function_stats': function_stats,
            'generated_at': utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting chatbot analytics: {e}")
        return {}
