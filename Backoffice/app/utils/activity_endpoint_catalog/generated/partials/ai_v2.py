"""
AUTO-GENERATED — blueprint 'ai_v2'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("POST", "ai_v2.append_conversation_message"): ActivityEndpointSpec(description="Completed Append Conversation Message", activity_type="admin_ai"),
    ("POST", "ai_v2.cancel_chat_stream"): ActivityEndpointSpec(description="Cancelled Chat Stream", activity_type="admin_ai"),
    ("POST", "ai_v2.clear_conversation_inflight"): ActivityEndpointSpec(description="Cleared Conversation Inflight", activity_type="admin_ai"),
    ("POST", "ai_v2.export_table_as_excel"): ActivityEndpointSpec(description="Exported Table As Excel", activity_type="admin_ai"),
    ("POST", "ai_v2.import_conversation_messages"): ActivityEndpointSpec(description="Imported Conversation Messages", activity_type="admin_ai"),
    ("POST", "ai_v2.submit_feedback"): ActivityEndpointSpec(description="Submitted Feedback", activity_type="admin_ai"),
}

