"""Entity permission management routes (NS hierarchy, secretariat, entity grants)."""

from collections import defaultdict

from flask import request, current_app

from app import db
from app.models import User, Country, UserEntityPermission, NSBranch, NSSubBranch, NSLocalUnit, SecretariatDivision, SecretariatDepartment
from app.models.organization import SecretariatRegionalOffice, SecretariatClusterOffice
from app.models.enums import EntityType
from app.routes.admin.shared import permission_required
from app.services.entity_service import EntityService
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import json_bad_request, json_not_found, json_ok, json_ok_result, json_server_error, json_error, require_json_keys
from app.utils.error_handling import handle_json_view_exception
from app.utils.sql_utils import safe_ilike_pattern

from . import bp


# === Entity Permission Management Routes ===

@bp.route("/users/<int:user_id>/entities", methods=["GET"])
@permission_required('admin.users.grants.manage')
def get_user_entities(user_id):
    """Get all entities assigned to a user."""
    user = User.query.get_or_404(user_id)

    # Get all entity permissions for this user
    entity_permissions = UserEntityPermission.query.filter_by(user_id=user_id).all()

    entities_data = []
    for perm in entity_permissions:
        entity = EntityService.get_entity(perm.entity_type, perm.entity_id)
        if entity:
            entities_data.append({
                'permission_id': perm.id,
                'entity_type': perm.entity_type,
                'entity_id': perm.entity_id,
                'entity_name': EntityService.get_entity_name(perm.entity_type, perm.entity_id, include_hierarchy=True)
            })

    return json_ok(entities=entities_data)

@bp.route("/users/<int:user_id>/entities/add", methods=["POST"])
@permission_required('admin.users.grants.manage')
def add_user_entity(user_id):
    """Add an entity permission to a user."""
    try:
        user = User.query.get_or_404(user_id)

        data = get_json_safe()
        err = require_json_keys(data, ['entity_type', 'entity_id'])
        if err:
            return err

        entity_type = data.get('entity_type')
        entity_id = data.get('entity_id')

        if not entity_type or not str(entity_type).strip():
            return json_bad_request('entity_type is required')

        # Convert entity_id to int if it's a string
        try:
            entity_id = int(entity_id)
        except (ValueError, TypeError):
            return json_bad_request('entity_id must be a valid integer')

        # Validate entity exists
        entity = EntityService.get_entity(entity_type, entity_id)
        if not entity:
            return json_not_found('Entity not found')

        # Check if permission already exists
        existing_perm = UserEntityPermission.query.filter_by(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id
        ).first()

        if existing_perm:
            return json_error('Permission already exists', 409)

        # Create new permission
        new_perm = UserEntityPermission(
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id
        )
        db.session.add(new_perm)

        # For country entities, also add to legacy user.countries
        if entity_type == EntityType.country.value:
            country = Country.query.get(entity_id)
            if country and country not in user.countries:
                user.countries.append(country)

        db.session.flush()

        return json_ok(
            permission_id=new_perm.id,
            entity_name=EntityService.get_entity_name(entity_type, entity_id, include_hierarchy=True),
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/users/<int:user_id>/entities/remove/<int:permission_id>", methods=["DELETE"])
@permission_required('admin.users.grants.manage')
def remove_user_entity(user_id, permission_id):
    """Remove an entity permission from a user."""
    try:
        user = User.query.get_or_404(user_id)
        perm = UserEntityPermission.query.filter_by(id=permission_id, user_id=user_id).first_or_404()

        # For country entities, also remove from legacy user.countries
        if perm.entity_type == EntityType.country.value:
            country = Country.query.get(perm.entity_id)
            if country and country in user.countries:
                user.countries.remove(country)

        db.session.delete(perm)
        db.session.flush()

        return json_ok()
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/entities/search", methods=["GET"])
@permission_required('admin.users.grants.manage')
def search_entities():
    """Search for entities of a specific type."""
    entity_type = request.args.get('type')
    query = request.args.get('q', '').strip()

    if not entity_type:
        return json_bad_request('entity type is required')

    results = []

    try:
        safe_pattern = safe_ilike_pattern(query)
        if entity_type == EntityType.country.value:
            entities = Country.query.filter(Country.name.ilike(safe_pattern)).order_by(Country.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': entity.name,
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.national_society.value:
            from app.models.organization import NationalSociety
            entities = NationalSociety.query.filter_by(is_active=True).join(Country).filter(
                db.or_(
                    NationalSociety.name.ilike(safe_pattern),
                    Country.name.ilike(safe_pattern)
                )
            ).order_by(Country.name, NationalSociety.name).limit(20).all()
            for entity in entities:
                country_name = entity.country.name if entity.country else ""
                display_name = f"{entity.name} ({country_name})" if country_name else entity.name
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': display_name,
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.ns_branch.value:
            entities = NSBranch.query.join(Country).filter(
                db.or_(
                    NSBranch.name.ilike(safe_pattern),
                    Country.name.ilike(safe_pattern)
                )
            ).order_by(Country.name, NSBranch.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': EntityService.get_entity_name(entity_type, entity.id, include_hierarchy=True),
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.ns_subbranch.value:
            entities = NSSubBranch.query.join(NSBranch).join(Country).filter(
                NSSubBranch.name.ilike(safe_pattern)
            ).order_by(Country.name, NSBranch.name, NSSubBranch.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': EntityService.get_entity_name(entity_type, entity.id, include_hierarchy=True),
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.division.value:
            entities = SecretariatDivision.query.filter(
                SecretariatDivision.name.ilike(safe_pattern)
            ).order_by(SecretariatDivision.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': entity.name,
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.department.value:
            entities = SecretariatDepartment.query.join(SecretariatDivision).filter(
                db.or_(
                    SecretariatDepartment.name.ilike(safe_pattern),
                    SecretariatDivision.name.ilike(safe_pattern)
                )
            ).order_by(SecretariatDivision.name, SecretariatDepartment.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': EntityService.get_entity_name(entity_type, entity.id, include_hierarchy=True),
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.regional_office.value:
            entities = SecretariatRegionalOffice.query.filter(
                SecretariatRegionalOffice.name.ilike(safe_pattern)
            ).order_by(SecretariatRegionalOffice.display_order, SecretariatRegionalOffice.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': entity.name,
                    'entity_type': entity_type
                })

        elif entity_type == EntityType.cluster_office.value:
            entities = SecretariatClusterOffice.query.join(SecretariatRegionalOffice).filter(
                db.or_(
                    SecretariatClusterOffice.name.ilike(safe_pattern),
                    SecretariatRegionalOffice.name.ilike(safe_pattern)
                )
            ).order_by(SecretariatRegionalOffice.name, SecretariatClusterOffice.name).limit(20).all()
            for entity in entities:
                results.append({
                    'id': entity.id,
                    'name': entity.name,
                    'display_name': EntityService.get_entity_name(entity_type, entity.id, include_hierarchy=True),
                    'entity_type': entity_type
                })

        return json_ok(results=results)

    except Exception as e:
        return json_server_error(GENERIC_ERROR_MESSAGE)

@bp.route("/structure/ns-hierarchy", methods=["GET"])
@permission_required('admin.users.grants.manage')
def get_ns_hierarchy():
    """Get NS structure hierarchy. If country_id provided, return branches-only for that country; otherwise grouped by country."""
    try:
        country_id = request.args.get('country_id', type=int)

        def build_branch_tree_for_country(country):
            items = []
            branches = NSBranch.query.filter_by(country_id=country.id, is_active=True).order_by(NSBranch.name).all()
            for branch in branches:
                branch_data = {
                    'id': branch.id,
                    'name': branch.name,
                    'code': branch.code,
                    'type': 'ns_branch',
                    'parent_id': country.id,
                    'children': []
                }
                subbranches = NSSubBranch.query.filter_by(branch_id=branch.id, is_active=True).order_by(NSSubBranch.name).all()
                for subbranch in subbranches:
                    subbranch_data = {
                        'id': subbranch.id,
                        'name': subbranch.name,
                        'code': subbranch.code,
                        'type': 'ns_subbranch',
                        'parent_id': branch.id,
                        'children': []
                    }
                    local_units = NSLocalUnit.query.filter_by(
                        branch_id=branch.id,
                        subbranch_id=subbranch.id,
                        is_active=True
                    ).order_by(NSLocalUnit.name).all()
                    for local_unit in local_units:
                        subbranch_data['children'].append({
                            'id': local_unit.id,
                            'name': local_unit.name,
                            'code': local_unit.code,
                            'type': 'ns_localunit',
                            'parent_id': subbranch.id
                        })
                    branch_data['children'].append(subbranch_data)
                direct_local_units = NSLocalUnit.query.filter(
                    NSLocalUnit.branch_id == branch.id,
                    NSLocalUnit.subbranch_id.is_(None),
                    NSLocalUnit.is_active == True
                ).order_by(NSLocalUnit.name).all()
                for local_unit in direct_local_units:
                    branch_data['children'].append({
                        'id': local_unit.id,
                        'name': local_unit.name,
                        'code': local_unit.code,
                        'type': 'ns_localunit',
                        'parent_id': branch.id
                    })
                items.append(branch_data)
            return items

        # If a country_id is provided, return a flat list of branches for that country
        if country_id:
            country = Country.query.get_or_404(country_id)
            hierarchy = build_branch_tree_for_country(country)
            return json_ok(hierarchy=hierarchy)

        # Default: grouped by country for backward compatibility
        countries = Country.query.order_by(Country.name).all()
        hierarchy = []
        for country in countries:
            children = build_branch_tree_for_country(country)
            if children:
                hierarchy.append({
                    'id': country.id,
                    'name': country.name,
                    'type': 'country',
                    'children': children
                })
        return json_ok(hierarchy=hierarchy)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/structure/secretariat-hierarchy", methods=["GET"])
@permission_required('admin.users.grants.manage')
def get_secretariat_hierarchy():
    """Get Secretariat structure hierarchy (divisions and departments)."""
    try:
        # Get all divisions (avoid eager loading on dynamic relationships)
        divisions = SecretariatDivision.query.filter_by(is_active=True).order_by(SecretariatDivision.display_order, SecretariatDivision.name).all()

        hierarchy = []
        for division in divisions:
            division_data = {
                'id': division.id,
                'name': division.name,
                'code': division.code,
                'type': 'division',
                'children': []
            }

            # Get departments for this division
            departments = SecretariatDepartment.query.filter_by(
                division_id=division.id,
                is_active=True
            ).order_by(SecretariatDepartment.display_order, SecretariatDepartment.name).all()

            for department in departments:
                division_data['children'].append({
                    'id': department.id,
                    'name': department.name,
                    'code': department.code,
                    'type': 'department',
                    'parent_id': division.id
                })

            hierarchy.append(division_data)

        return json_ok(hierarchy=hierarchy)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/entities/hierarchical", methods=["GET"])
@permission_required('admin.users.grants.manage')
def get_hierarchical_entities():
    """Get all entities grouped hierarchically for entity selection."""
    try:
        entity_types = request.args.getlist('types')  # List of entity types to include

        if not entity_types:
            return json_bad_request('At least one entity type must be specified')

        result = {}

        # Countries grouped by region
        if 'country' in entity_types:
            countries_by_region = defaultdict(list)
            countries = Country.query.order_by(Country.region, Country.name).all()
            for country in countries:
                region = country.region if country.region else "Unassigned Region"
                countries_by_region[region].append({
                    'id': country.id,
                    'name': country.name,
                    'type': 'country',
                    'entity_type': 'country'
                })
            result['countries'] = dict(countries_by_region)

        # National Societies grouped by country
        if 'national_society' in entity_types:
            from app.models.organization import NationalSociety
            national_societies_by_country = defaultdict(list)
            national_societies = NationalSociety.query.filter_by(is_active=True).join(Country).order_by(Country.name, NationalSociety.name).all()
            for ns in national_societies:
                country_name = ns.country.name if ns.country else "Unknown"
                national_societies_by_country[country_name].append({
                    'id': ns.id,
                    'name': ns.name,
                    'type': 'national_society',
                    'entity_type': 'national_society',
                    'country_id': ns.country_id
                })
            result['national_societies'] = dict(national_societies_by_country)

        # NS Branches grouped by country
        if 'ns_branch' in entity_types:
            ns_branches_by_country = defaultdict(list)
            branches = NSBranch.query.filter_by(is_active=True).join(Country).order_by(Country.name, NSBranch.name).all()
            for branch in branches:
                country_name = branch.country.name if branch.country else "Unknown"
                ns_branches_by_country[country_name].append({
                    'id': branch.id,
                    'name': branch.name,
                    'type': 'ns_branch',
                    'entity_type': 'ns_branch',
                    'country_id': branch.country_id
                })
            result['ns_branches'] = dict(ns_branches_by_country)

        # NS Sub-branches grouped by country (via branch)
        if 'ns_subbranch' in entity_types:
            ns_subbranches_by_country = defaultdict(list)
            subbranches = NSSubBranch.query.filter_by(is_active=True).join(NSBranch).join(Country).order_by(Country.name, NSBranch.name, NSSubBranch.name).all()
            for subbranch in subbranches:
                country_name = subbranch.branch.country.name if subbranch.branch and subbranch.branch.country else "Unknown"
                ns_subbranches_by_country[country_name].append({
                    'id': subbranch.id,
                    'name': subbranch.name,
                    'type': 'ns_subbranch',
                    'entity_type': 'ns_subbranch',
                    'branch_id': subbranch.branch_id,
                    'country_id': subbranch.branch.country_id if subbranch.branch else None
                })
            result['ns_subbranches'] = dict(ns_subbranches_by_country)

        # NS Local Units grouped by country (via branch)
        if 'ns_localunit' in entity_types:
            ns_localunits_by_country = defaultdict(list)
            local_units = NSLocalUnit.query.filter_by(is_active=True).join(NSBranch).join(Country).order_by(Country.name, NSBranch.name, NSLocalUnit.name).all()
            for local_unit in local_units:
                country_name = local_unit.branch.country.name if local_unit.branch and local_unit.branch.country else "Unknown"
                ns_localunits_by_country[country_name].append({
                    'id': local_unit.id,
                    'name': local_unit.name,
                    'type': 'ns_localunit',
                    'entity_type': 'ns_localunit',
                    'branch_id': local_unit.branch_id,
                    'country_id': local_unit.branch.country_id if local_unit.branch else None
                })
            result['ns_localunits'] = dict(ns_localunits_by_country)

        # Divisions (top level, no grouping)
        if 'division' in entity_types:
            divisions = SecretariatDivision.query.filter_by(is_active=True).order_by(SecretariatDivision.display_order, SecretariatDivision.name).all()
            result['divisions'] = [{
                'id': div.id,
                'name': div.name,
                'type': 'division',
                'entity_type': 'division'
            } for div in divisions]

        # Departments grouped by division
        if 'department' in entity_types:
            departments_by_division = defaultdict(list)
            departments = SecretariatDepartment.query.filter_by(is_active=True).join(SecretariatDivision).order_by(SecretariatDivision.name, SecretariatDepartment.name).all()
            for dept in departments:
                division_name = dept.division.name if dept.division else "Unknown"
                departments_by_division[division_name].append({
                    'id': dept.id,
                    'name': dept.name,
                    'type': 'department',
                    'entity_type': 'department',
                    'division_id': dept.division_id
                })
            result['departments'] = dict(departments_by_division)

        # Regional Offices (top level, no grouping)
        if 'regional_office' in entity_types:
            regional_offices = SecretariatRegionalOffice.query.filter_by(is_active=True).order_by(SecretariatRegionalOffice.display_order, SecretariatRegionalOffice.name).all()
            result['regional_offices'] = [{
                'id': ro.id,
                'name': ro.name,
                'type': 'regional_office',
                'entity_type': 'regional_office'
            } for ro in regional_offices]

        # Cluster Offices grouped by regional office
        if 'cluster_office' in entity_types:
            cluster_offices_by_region = defaultdict(list)
            cluster_offices = SecretariatClusterOffice.query.filter_by(is_active=True).join(SecretariatRegionalOffice).order_by(SecretariatRegionalOffice.name, SecretariatClusterOffice.name).all()
            for co in cluster_offices:
                region_name = co.regional_office.name if co.regional_office else "Unknown"
                cluster_offices_by_region[region_name].append({
                    'id': co.id,
                    'name': co.name,
                    'type': 'cluster_office',
                    'entity_type': 'cluster_office',
                    'regional_office_id': co.regional_office_id
                })
            result['cluster_offices'] = dict(cluster_offices_by_region)

        return json_ok_result(result)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)

@bp.route("/structure/secretariat-regions-hierarchy", methods=["GET"])
@permission_required('admin.users.grants.manage')
def get_secretariat_regions_hierarchy():
    """Get Secretariat Regions hierarchy (regional offices > cluster offices)."""
    try:
        # Load regional offices
        regions = SecretariatRegionalOffice.query.filter_by(is_active=True).order_by(SecretariatRegionalOffice.display_order, SecretariatRegionalOffice.name).all()

        hierarchy = []
        for region in regions:
            node = {
                'id': region.id,
                'name': region.name,
                'code': region.code,
                'type': 'regional_office',
                'children': []
            }

            clusters = SecretariatClusterOffice.query.filter_by(regional_office_id=region.id, is_active=True) \
                .order_by(SecretariatClusterOffice.display_order, SecretariatClusterOffice.name).all()
            for cluster in clusters:
                node['children'].append({
                    'id': cluster.id,
                    'name': cluster.name,
                    'code': cluster.code,
                    'type': 'cluster_office',
                    'parent_id': region.id
                })

            hierarchy.append(node)

        return json_ok(hierarchy=hierarchy)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
