"""
AUTO-GENERATED — blueprint 'content_management'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "content_management.resource_subcategory_api_delete"): ActivityEndpointSpec(description="Deleted Resource Subcategory Api Delete", activity_type="admin_content"),
    ("POST", "content_management.approve_document"): ActivityEndpointSpec(description="Approved Document", activity_type="admin_content"),
    ("POST", "content_management.decline_document"): ActivityEndpointSpec(description="Declined Document", activity_type="admin_content"),
    ("POST", "content_management.delete_document"): ActivityEndpointSpec(description="Deleted Document", activity_type="admin_content"),
    ("POST", "content_management.delete_document_thumbnail"): ActivityEndpointSpec(description="Deleted Document Thumbnail", activity_type="admin_content"),
    ("POST", "content_management.delete_resource"): ActivityEndpointSpec(description="Deleted Resource", activity_type="admin_content"),
    ("POST", "content_management.delete_resource_subgroup"): ActivityEndpointSpec(description="Deleted Resource Subgroup", activity_type="admin_content"),
    ("POST", "content_management.delete_resource_thumbnail"): ActivityEndpointSpec(description="Deleted Resource Thumbnail", activity_type="admin_content"),
    ("POST", "content_management.edit_document"): ActivityEndpointSpec(description="Edited Document", activity_type="admin_content"),
    ("POST", "content_management.edit_resource"): ActivityEndpointSpec(description="Edited Resource", activity_type="admin_content"),
    ("POST", "content_management.edit_resource_subgroup"): ActivityEndpointSpec(description="Edited Resource Subgroup", activity_type="admin_content"),
    ("POST", "content_management.generate_document_thumbnail"): ActivityEndpointSpec(description="Generated Document Thumbnail", activity_type="admin_content"),
    ("POST", "content_management.generate_resource_thumbnail"): ActivityEndpointSpec(description="Generated Resource Thumbnail", activity_type="admin_content"),
    ("POST", "content_management.new_resource"): ActivityEndpointSpec(description="Created Resource", activity_type="admin_content"),
    ("POST", "content_management.new_resource_subgroup"): ActivityEndpointSpec(description="Created Resource Subgroup", activity_type="admin_content"),
    ("POST", "content_management.resource_subcategory_api_create"): ActivityEndpointSpec(description="Completed Resource Subcategory Api Create", activity_type="admin_content"),
    ("POST", "content_management.upload_document"): ActivityEndpointSpec(description="Completed Upload Document", activity_type="admin_content"),
    ("PUT", "content_management.resource_subcategory_api_update"): ActivityEndpointSpec(description="Updated Resource Subcategory Api Update", activity_type="admin_content"),
}

