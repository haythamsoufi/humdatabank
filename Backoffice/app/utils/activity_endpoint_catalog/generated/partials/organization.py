"""
AUTO-GENERATED — blueprint 'organization'. Do not edit by hand.
Regenerate: python scripts/generate_activity_endpoint_catalog.py
"""

from __future__ import annotations

from app.utils.activity_endpoint_catalog.spec import ActivityEndpointSpec


SPECS: dict[tuple[str, str], ActivityEndpointSpec] = {
    ("DELETE", "organization.api_remove_part_of_program"): ActivityEndpointSpec(description="Removed Part Of Program", activity_type="admin_organization"),
    ("POST", "organization.api_add_part_of_program"): ActivityEndpointSpec(description="Added Part Of Program", activity_type="admin_organization"),
    ("POST", "organization.api_update_ns_part_of"): ActivityEndpointSpec(description="Updated Ns Part Of", activity_type="admin_organization"),
    ("POST", "organization.delete_country"): ActivityEndpointSpec(description="Deleted Country", activity_type="admin_organization"),
    ("POST", "organization.delete_national_society"): ActivityEndpointSpec(description="Deleted National Society", activity_type="admin_organization"),
    ("POST", "organization.delete_ns_branch"): ActivityEndpointSpec(description="Deleted Ns Branch", activity_type="admin_organization"),
    ("POST", "organization.delete_ns_localunit"): ActivityEndpointSpec(description="Deleted Ns Localunit", activity_type="admin_organization"),
    ("POST", "organization.delete_ns_subbranch"): ActivityEndpointSpec(description="Deleted Ns Subbranch", activity_type="admin_organization"),
    ("POST", "organization.delete_secretariat_cluster_office"): ActivityEndpointSpec(description="Deleted Secretariat Cluster Office", activity_type="admin_organization"),
    ("POST", "organization.delete_secretariat_department"): ActivityEndpointSpec(description="Deleted Secretariat Department", activity_type="admin_organization"),
    ("POST", "organization.delete_secretariat_division"): ActivityEndpointSpec(description="Deleted Secretariat Division", activity_type="admin_organization"),
    ("POST", "organization.delete_secretariat_regional_office"): ActivityEndpointSpec(description="Deleted Secretariat Regional Office", activity_type="admin_organization"),
    ("POST", "organization.edit_country"): ActivityEndpointSpec(description="Edited Country", activity_type="admin_organization"),
    ("POST", "organization.edit_national_society"): ActivityEndpointSpec(description="Edited National Society", activity_type="admin_organization"),
    ("POST", "organization.edit_ns_branch"): ActivityEndpointSpec(description="Edited Ns Branch", activity_type="admin_organization"),
    ("POST", "organization.edit_ns_localunit"): ActivityEndpointSpec(description="Edited Ns Localunit", activity_type="admin_organization"),
    ("POST", "organization.edit_ns_subbranch"): ActivityEndpointSpec(description="Edited Ns Subbranch", activity_type="admin_organization"),
    ("POST", "organization.edit_secretariat_cluster_office"): ActivityEndpointSpec(description="Edited Secretariat Cluster Office", activity_type="admin_organization"),
    ("POST", "organization.edit_secretariat_department"): ActivityEndpointSpec(description="Edited Secretariat Department", activity_type="admin_organization"),
    ("POST", "organization.edit_secretariat_division"): ActivityEndpointSpec(description="Edited Secretariat Division", activity_type="admin_organization"),
    ("POST", "organization.edit_secretariat_regional_office"): ActivityEndpointSpec(description="Edited Secretariat Regional Office", activity_type="admin_organization"),
    ("POST", "organization.import_countries"): ActivityEndpointSpec(description="Imported Countries", activity_type="admin_organization"),
    ("POST", "organization.import_national_societies"): ActivityEndpointSpec(description="Imported National Societies", activity_type="admin_organization"),
    ("POST", "organization.new_country"): ActivityEndpointSpec(description="Created Country", activity_type="admin_organization"),
    ("POST", "organization.new_national_society"): ActivityEndpointSpec(description="Created National Society", activity_type="admin_organization"),
    ("POST", "organization.new_ns_branch"): ActivityEndpointSpec(description="Created Ns Branch", activity_type="admin_organization"),
    ("POST", "organization.new_ns_localunit"): ActivityEndpointSpec(description="Created Ns Localunit", activity_type="admin_organization"),
    ("POST", "organization.new_ns_subbranch"): ActivityEndpointSpec(description="Created Ns Subbranch", activity_type="admin_organization"),
    ("POST", "organization.new_secretariat_cluster_office"): ActivityEndpointSpec(description="Created Secretariat Cluster Office", activity_type="admin_organization"),
    ("POST", "organization.new_secretariat_department"): ActivityEndpointSpec(description="Created Secretariat Department", activity_type="admin_organization"),
    ("POST", "organization.new_secretariat_division"): ActivityEndpointSpec(description="Created Secretariat Division", activity_type="admin_organization"),
    ("POST", "organization.new_secretariat_regional_office"): ActivityEndpointSpec(description="Created Secretariat Regional Office", activity_type="admin_organization"),
    ("PUT", "organization.api_update_ns_part_of"): ActivityEndpointSpec(description="Updated Ns Part Of", activity_type="admin_organization"),
}

