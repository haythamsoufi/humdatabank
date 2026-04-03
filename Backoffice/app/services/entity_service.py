"""
Entity Service - Centralized service for multi-level organizational entity operations.

This service provides a unified interface for working with different entity types
(countries, NS branches/sub-branches/local units, secretariat divisions/departments).
"""
from app.models import db
from app.models.core import Country
from app.models.organization import NationalSociety, NSBranch, NSSubBranch, NSLocalUnit, SecretariatDivision, SecretariatDepartment, SecretariatRegionalOffice, SecretariatClusterOffice
from app.models.enums import EntityType


class EntityService:
    """Service class for entity operations across all organizational levels."""

    # Mapping of entity types to their model classes
    ENTITY_MODEL_MAP = {
        EntityType.country.value: Country,
        EntityType.national_society.value: NationalSociety,
        EntityType.ns_branch.value: NSBranch,
        EntityType.ns_subbranch.value: NSSubBranch,
        EntityType.ns_localunit.value: NSLocalUnit,
        EntityType.division.value: SecretariatDivision,
        EntityType.department.value: SecretariatDepartment,
        EntityType.regional_office.value: SecretariatRegionalOffice,
        EntityType.cluster_office.value: SecretariatClusterOffice,
    }

    # Group order for document modal <optgroup> (matches components/entity_dropdown.html + national_society).
    DOCUMENT_MODAL_ENTITY_GROUP_ORDER = (
        EntityType.country.value,
        EntityType.national_society.value,
        EntityType.ns_branch.value,
        EntityType.ns_subbranch.value,
        EntityType.ns_localunit.value,
        EntityType.division.value,
        EntityType.department.value,
        EntityType.regional_office.value,
        EntityType.cluster_office.value,
    )

    @staticmethod
    def sort_document_modal_entity_choice_rows(rows):
        """Sort by entity type group (dashboard order), then label within group."""
        order = {t: i for i, t in enumerate(EntityService.DOCUMENT_MODAL_ENTITY_GROUP_ORDER)}

        def _key(r):
            et = (r.get("entity_type") or "").strip()
            return (order.get(et, len(order)), (r.get("label") or "").casefold())

        rows.sort(key=_key)
        return rows

    @staticmethod
    def get_entity(entity_type, entity_id):
        """Fetch entity object by type and ID.

        Args:
            entity_type (str): Entity type ('country', 'ns_branch', etc.)
            entity_id (int): Entity ID

        Returns:
            Model instance or None if not found
        """
        model_class = EntityService.ENTITY_MODEL_MAP.get(entity_type)
        if not model_class:
            return None

        return model_class.query.get(entity_id)

    @staticmethod
    def get_entity_display_name(entity_type, entity_id):
        """Get formatted display name for an entity.

        Args:
            entity_type (str): Entity type
            entity_id (int): Entity ID

        Returns:
            str: Formatted display name or 'Unknown Entity'
        """
        entity = EntityService.get_entity(entity_type, entity_id)
        if not entity:
            return f"Unknown {entity_type} (ID: {entity_id})"

        return entity.name

    @staticmethod
    def get_entity_name(entity_type, entity_id, include_hierarchy=False):
        """Get entity name with optional hierarchy path.

        Args:
            entity_type (str): Entity type
            entity_id (int): Entity ID
            include_hierarchy (bool): If True, return full hierarchy path

        Returns:
            str: Entity name or hierarchy path
        """
        if include_hierarchy:
            return EntityService.get_entity_hierarchy(entity_type, entity_id)
        else:
            return EntityService.get_entity_display_name(entity_type, entity_id)

    @staticmethod
    def get_localized_entity_name(entity_type, entity_id, include_hierarchy=False):
        """Get localized entity name with optional hierarchy path.

        Args:
            entity_type (str): Entity type
            entity_id (int): Entity ID
            include_hierarchy (bool): If True, return full hierarchy path with localized names

        Returns:
            str: Localized entity name or hierarchy path
        """
        if include_hierarchy:
            return EntityService.get_localized_entity_hierarchy(entity_type, entity_id)
        else:
            return EntityService.get_localized_entity_display_name(entity_type, entity_id)

    @staticmethod
    def get_localized_entity_display_name(entity_type, entity_id):
        """Get localized display name for an entity.

        Args:
            entity_type (str): Entity type
            entity_id (int): Entity ID

        Returns:
            str: Localized display name or 'Unknown Entity'
        """
        entity = EntityService.get_entity(entity_type, entity_id)
        if not entity:
            return f"Unknown {entity_type} (ID: {entity_id})"

        # Use localized name for countries
        if entity_type == EntityType.country.value:
            from app.utils.form_localization import get_localized_country_name
            return get_localized_country_name(entity)

        # For other entity types, return the name (no translations yet)
        # This can be extended later when other entity types support translations
        return entity.name

    @staticmethod
    def get_localized_entity_hierarchy(entity_type, entity_id):
        """Get full localized hierarchy path for an entity.

        Args:
            entity_type (str): Entity type
            entity_id (int): Entity ID

        Returns:
            str: Localized hierarchy path (e.g., 'Kenya > Nairobi Branch > Downtown Sub-branch')
        """
        entity = EntityService.get_entity(entity_type, entity_id)
        if not entity:
            return f"Unknown {entity_type}"

        from app.utils.form_localization import get_localized_country_name
        hierarchy_parts = []

        if entity_type == EntityType.country.value:
            # Country is top level
            hierarchy_parts.append(get_localized_country_name(entity))

        elif entity_type == EntityType.ns_branch.value:
            # Branch: Country > Branch
            if hasattr(entity, 'country') and entity.country:
                hierarchy_parts.append(get_localized_country_name(entity.country))
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.ns_subbranch.value:
            # Sub-branch: Country > Branch > Sub-branch
            if hasattr(entity, 'branch') and entity.branch:
                if entity.branch.country:
                    hierarchy_parts.append(get_localized_country_name(entity.branch.country))
                hierarchy_parts.append(entity.branch.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.ns_localunit.value:
            # Local Unit: Country > Branch > [Sub-branch] > Local Unit
            if hasattr(entity, 'branch') and entity.branch:
                if entity.branch.country:
                    hierarchy_parts.append(get_localized_country_name(entity.branch.country))
                hierarchy_parts.append(entity.branch.name)
                if hasattr(entity, 'subbranch') and entity.subbranch:
                    hierarchy_parts.append(entity.subbranch.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.division.value:
            # Division is top level for Secretariat
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.department.value:
            # Department: Division > Department
            if hasattr(entity, 'division') and entity.division:
                hierarchy_parts.append(entity.division.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.regional_office.value:
            # Regional Office
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.cluster_office.value:
            # Cluster Office: Regional Office > Cluster Office
            if hasattr(entity, 'regional_office') and entity.regional_office:
                hierarchy_parts.append(entity.regional_office.name)
            hierarchy_parts.append(entity.name)

        return " > ".join(hierarchy_parts) if hierarchy_parts else entity.name

    @staticmethod
    def get_entity_hierarchy(entity_type, entity_id):
        """Get full hierarchy path for an entity.

        Args:
            entity_type (str): Entity type
            entity_id (int): Entity ID

        Returns:
            str: Hierarchy path (e.g., 'Kenya > Nairobi Branch > Downtown Sub-branch')
        """
        entity = EntityService.get_entity(entity_type, entity_id)
        if not entity:
            return f"Unknown {entity_type}"

        hierarchy_parts = []

        if entity_type == EntityType.country.value:
            # Country is top level
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.ns_branch.value:
            # Branch: Country > Branch
            if hasattr(entity, 'country') and entity.country:
                hierarchy_parts.append(entity.country.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.ns_subbranch.value:
            # Sub-branch: Country > Branch > Sub-branch
            if hasattr(entity, 'branch') and entity.branch:
                if entity.branch.country:
                    hierarchy_parts.append(entity.branch.country.name)
                hierarchy_parts.append(entity.branch.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.ns_localunit.value:
            # Local Unit: Country > Branch > [Sub-branch] > Local Unit
            if hasattr(entity, 'branch') and entity.branch:
                if entity.branch.country:
                    hierarchy_parts.append(entity.branch.country.name)
                hierarchy_parts.append(entity.branch.name)
                if hasattr(entity, 'subbranch') and entity.subbranch:
                    hierarchy_parts.append(entity.subbranch.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.division.value:
            # Division is top level for Secretariat (no 'Secretariat - ' prefix in display)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.department.value:
            # Department: Division > Department (without 'Secretariat - ' prefix)
            if hasattr(entity, 'division') and entity.division:
                hierarchy_parts.append(entity.division.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.regional_office.value:
            # Regional Office (without 'Secretariat - ' prefix)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.cluster_office.value:
            # Cluster Office: Regional Office > Cluster Office (without 'Secretariat - ' prefix)
            if hasattr(entity, 'regional_office') and entity.regional_office:
                hierarchy_parts.append(entity.regional_office.name)
            hierarchy_parts.append(entity.name)

        return " > ".join(hierarchy_parts) if hierarchy_parts else entity.name

    @staticmethod
    def get_country_for_entity(entity_type, entity_id):
        """Get the related country for any entity type.

        Args:
            entity_type (str): Entity type
            entity_id (int): Entity ID

        Returns:
            Country object or None
        """
        entity = EntityService.get_entity(entity_type, entity_id)
        if not entity:
            return None

        if entity_type == EntityType.country.value:
            # Entity is already a country
            return entity

        elif entity_type in [EntityType.ns_branch.value, EntityType.ns_subbranch.value, EntityType.ns_localunit.value]:
            # NS entities - trace back to country
            if entity_type == EntityType.ns_branch.value:
                return entity.country if hasattr(entity, 'country') else None
            elif entity_type == EntityType.ns_subbranch.value:
                return entity.branch.country if (hasattr(entity, 'branch') and entity.branch) else None
            elif entity_type == EntityType.ns_localunit.value:
                return entity.branch.country if (hasattr(entity, 'branch') and entity.branch) else None

        elif entity_type in [EntityType.division.value, EntityType.department.value, EntityType.regional_office.value, EntityType.cluster_office.value]:
            # Secretariat entities don't have a specific country
            return None

        return None

    @staticmethod
    def get_entities_for_user(user, entity_type=None):
        """Get all entities a user has access to.

        Args:
            user: User object
            entity_type (str, optional): Filter by entity type

        Returns:
            list: List of entity objects
        """
        from app.models.core import UserEntityPermission

        # Admins and system managers have access to all entities
        from app.services.authorization_service import AuthorizationService
        if AuthorizationService.is_admin(user):
            if entity_type:
                model_class = EntityService.ENTITY_MODEL_MAP.get(entity_type)
                if model_class:
                    return model_class.query.all()
                return []
            else:
                # Return all entities from all types
                all_entities = []
                for model_class in EntityService.ENTITY_MODEL_MAP.values():
                    all_entities.extend(model_class.query.all())
                return all_entities

        # For regular users, get from permissions
        query = UserEntityPermission.query.filter_by(user_id=user.id)
        if entity_type:
            query = query.filter_by(entity_type=entity_type)

        permissions = query.all()

        entities = []
        for perm in permissions:
            entity = EntityService.get_entity(perm.entity_type, perm.entity_id)
            if entity:
                entities.append(entity)

        return entities

    @staticmethod
    def check_user_entity_access(user, entity_type, entity_id):
        """Check if user has access to a specific entity.

        Args:
            user: User object
            entity_type (str): Entity type
            entity_id (int): Entity ID

        Returns:
            bool: True if user has access
        """
        # Admins and system managers have access to everything
        from app.services.authorization_service import AuthorizationService
        if AuthorizationService.is_admin(user):
            return True

        from app.models.core import UserEntityPermission

        return UserEntityPermission.query.filter_by(
            user_id=user.id,
            entity_type=entity_type,
            entity_id=entity_id
        ).first() is not None

    @staticmethod
    def get_all_entities_by_type(entity_type, filter_active=True):
        """Get all entities of a specific type.

        Args:
            entity_type (str): Entity type
            filter_active (bool): If True, only return active entities

        Returns:
            list: List of entity objects
        """
        model_class = EntityService.ENTITY_MODEL_MAP.get(entity_type)
        if not model_class:
            return []

        query = model_class.query

        # Apply active filter if the model has an is_active field
        if filter_active and hasattr(model_class, 'is_active'):
            query = query.filter_by(is_active=True)

        return query.all()

    @staticmethod
    def get_entity_type_label(entity_type):
        """Get human-readable label for entity type.

        Args:
            entity_type (str): Entity type

        Returns:
            str: Human-readable label
        """
        labels = {
            EntityType.country.value: "Country",
            EntityType.national_society.value: "National Society",
            EntityType.ns_branch.value: "NS Branch",
            EntityType.ns_subbranch.value: "NS Sub-branch",
            EntityType.ns_localunit.value: "NS Local Unit",
            EntityType.division.value: "Secretariat Division",
            EntityType.department.value: "Secretariat Department",
            EntityType.regional_office.value: "Regional Office",
            EntityType.cluster_office.value: "Cluster Office",
        }
        return labels.get(entity_type, entity_type.replace('_', ' ').title())

    @staticmethod
    def get_children_entities(entity_type, entity_id):
        """Get child entities for a parent entity.

        Args:
            entity_type (str): Parent entity type
            entity_id (int): Parent entity ID

        Returns:
            dict: Dictionary mapping child entity types to lists of child entities
        """
        entity = EntityService.get_entity(entity_type, entity_id)
        if not entity:
            return {}

        children = {}

        if entity_type == EntityType.country.value:
            # Country has NS branches as children
            if hasattr(entity, 'ns_branches'):
                children[EntityType.ns_branch.value] = list(entity.ns_branches.all())

        elif entity_type == EntityType.ns_branch.value:
            # Branch has sub-branches and local units as children
            if hasattr(entity, 'subbranches'):
                children[EntityType.ns_subbranch.value] = list(entity.subbranches.all())
            if hasattr(entity, 'local_units'):
                # Filter local units that don't have a sub-branch (direct children)
                direct_local_units = [lu for lu in entity.local_units.all() if not lu.subbranch_id]
                children[EntityType.ns_localunit.value] = direct_local_units

        elif entity_type == EntityType.ns_subbranch.value:
            # Sub-branch has local units as children
            if hasattr(entity, 'local_units'):
                children[EntityType.ns_localunit.value] = list(entity.local_units.all())

        elif entity_type == EntityType.division.value:
            # Division has departments as children
            if hasattr(entity, 'departments'):
                children[EntityType.department.value] = list(entity.departments.all())

        elif entity_type == EntityType.regional_office.value:
            # Regional Office has cluster offices as children
            if hasattr(entity, 'cluster_offices'):
                children[EntityType.cluster_office.value] = list(entity.cluster_offices.all())

        return children
