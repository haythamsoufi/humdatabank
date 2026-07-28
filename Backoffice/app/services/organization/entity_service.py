"""
Entity Service - Centralized service for multi-level organizational entity operations.

This service provides a unified interface for working with different entity types
(countries, NS branches/sub-branches/local units, secretariat divisions/departments).
"""
from collections import defaultdict

from sqlalchemy.orm import joinedload

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

    # Eager-load options for hierarchy display (avoids lazy loads on parent relations).
    #
    # Built lazily (on first use) rather than as a class-body dict literal.
    # Constructing joinedload(NSBranch.country) etc. touches mapped attributes,
    # which can force SQLAlchemy to run configure_mappers() across the *whole*
    # declarative registry. Doing that unconditionally at module-import time
    # (i.e. whenever entity_service.py is first imported, from
    # template_context.py during app boot) previously raced a background
    # thread that was still mid-import of app/models/embeddings.py, causing
    # an intermittent "failed to locate a name ('AIEmbedding')" boot crash.
    # App startup now eagerly configures all mappers before any thread starts
    # (see app.bootstrap._configure_all_model_mappers), which is the primary
    # fix; building this dict lazily is a defensive second layer so importing
    # this module alone never has side effects on the ORM registry.
    _HIERARCHY_LOAD_OPTIONS_CACHE = None

    @classmethod
    def _get_hierarchy_load_options(cls):
        if cls._HIERARCHY_LOAD_OPTIONS_CACHE is None:
            cls._HIERARCHY_LOAD_OPTIONS_CACHE = {
                EntityType.ns_branch.value: (joinedload(NSBranch.country),),
                EntityType.ns_subbranch.value: (
                    joinedload(NSSubBranch.branch).joinedload(NSBranch.country),
                ),
                EntityType.ns_localunit.value: (
                    joinedload(NSLocalUnit.branch).joinedload(NSBranch.country),
                    joinedload(NSLocalUnit.subbranch),
                ),
                EntityType.department.value: (joinedload(SecretariatDepartment.division),),
                EntityType.cluster_office.value: (
                    joinedload(SecretariatClusterOffice.regional_office),
                ),
            }
        return cls._HIERARCHY_LOAD_OPTIONS_CACHE

    @staticmethod
    def _normalize_entity_pair(entity_type, entity_id):
        """Return (entity_type, int_id) or None if invalid."""
        if not entity_type or entity_id is None:
            return None
        try:
            return (str(entity_type), int(entity_id))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def prefetch_entities(pairs, include_hierarchy=True):
        """Batch-fetch entities grouped by type.

        Args:
            pairs: Iterable of (entity_type, entity_id) tuples.
            include_hierarchy (bool): Eager-load parent relations needed for hierarchy names.

        Returns:
            dict: Mapping of (entity_type, entity_id) -> model instance.
        """
        ids_by_type = defaultdict(set)
        for entity_type, entity_id in pairs or []:
            normalized = EntityService._normalize_entity_pair(entity_type, entity_id)
            if normalized:
                ids_by_type[normalized[0]].add(normalized[1])

        result = {}
        for entity_type, entity_ids in ids_by_type.items():
            model_class = EntityService.ENTITY_MODEL_MAP.get(entity_type)
            if not model_class or not entity_ids:
                continue

            query = model_class.query.filter(model_class.id.in_(entity_ids))
            if include_hierarchy:
                for option in EntityService._get_hierarchy_load_options().get(entity_type, ()):
                    query = query.options(option)

            for entity in query.all():
                result[(entity_type, entity.id)] = entity

        return result

    @staticmethod
    def _display_name_from_entity(entity_type, entity):
        """Plain display name from a loaded entity object."""
        if not entity:
            return None
        return entity.name

    @staticmethod
    def _localized_display_name_from_entity(entity_type, entity):
        """Localized plain display name from a loaded entity object."""
        if not entity:
            return None
        if entity_type == EntityType.country.value:
            from app.utils.form_localization import get_localized_country_name
            return get_localized_country_name(entity)
        return entity.name

    @staticmethod
    def _hierarchy_from_entity(entity_type, entity):
        """Hierarchy path from a loaded entity object (non-localized)."""
        if not entity:
            return f"Unknown {entity_type}"

        hierarchy_parts = []

        if entity_type == EntityType.country.value:
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.ns_branch.value:
            if hasattr(entity, 'country') and entity.country:
                hierarchy_parts.append(entity.country.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.ns_subbranch.value:
            if hasattr(entity, 'branch') and entity.branch:
                if entity.branch.country:
                    hierarchy_parts.append(entity.branch.country.name)
                hierarchy_parts.append(entity.branch.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.ns_localunit.value:
            if hasattr(entity, 'branch') and entity.branch:
                if entity.branch.country:
                    hierarchy_parts.append(entity.branch.country.name)
                hierarchy_parts.append(entity.branch.name)
                if hasattr(entity, 'subbranch') and entity.subbranch:
                    hierarchy_parts.append(entity.subbranch.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.division.value:
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.department.value:
            if hasattr(entity, 'division') and entity.division:
                hierarchy_parts.append(entity.division.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.regional_office.value:
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.cluster_office.value:
            if hasattr(entity, 'regional_office') and entity.regional_office:
                hierarchy_parts.append(entity.regional_office.name)
            hierarchy_parts.append(entity.name)

        return " > ".join(hierarchy_parts) if hierarchy_parts else entity.name

    @staticmethod
    def _localized_hierarchy_from_entity(entity_type, entity):
        """Localized hierarchy path from a loaded entity object."""
        if not entity:
            return f"Unknown {entity_type}"

        from app.utils.form_localization import get_localized_country_name
        hierarchy_parts = []

        if entity_type == EntityType.country.value:
            hierarchy_parts.append(get_localized_country_name(entity))

        elif entity_type == EntityType.ns_branch.value:
            if hasattr(entity, 'country') and entity.country:
                hierarchy_parts.append(get_localized_country_name(entity.country))
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.ns_subbranch.value:
            if hasattr(entity, 'branch') and entity.branch:
                if entity.branch.country:
                    hierarchy_parts.append(get_localized_country_name(entity.branch.country))
                hierarchy_parts.append(entity.branch.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.ns_localunit.value:
            if hasattr(entity, 'branch') and entity.branch:
                if entity.branch.country:
                    hierarchy_parts.append(get_localized_country_name(entity.branch.country))
                hierarchy_parts.append(entity.branch.name)
                if hasattr(entity, 'subbranch') and entity.subbranch:
                    hierarchy_parts.append(entity.subbranch.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.division.value:
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.department.value:
            if hasattr(entity, 'division') and entity.division:
                hierarchy_parts.append(entity.division.name)
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.regional_office.value:
            hierarchy_parts.append(entity.name)

        elif entity_type == EntityType.cluster_office.value:
            if hasattr(entity, 'regional_office') and entity.regional_office:
                hierarchy_parts.append(entity.regional_office.name)
            hierarchy_parts.append(entity.name)

        return " > ".join(hierarchy_parts) if hierarchy_parts else entity.name

    @staticmethod
    def _name_from_entity(entity_type, entity, include_hierarchy=False, localized=False):
        """Resolve display or hierarchy name from a loaded entity."""
        if not entity:
            if localized:
                return f"Unknown {entity_type} (ID: unknown)"
            return f"Unknown {entity_type}"

        if include_hierarchy:
            if localized:
                return EntityService._localized_hierarchy_from_entity(entity_type, entity)
            return EntityService._hierarchy_from_entity(entity_type, entity)

        if localized:
            return EntityService._localized_display_name_from_entity(entity_type, entity)
        return EntityService._display_name_from_entity(entity_type, entity)

    @staticmethod
    def batch_entity_names(pairs, include_hierarchy=False, localized=False, prefetched=None):
        """Batch-resolve entity display names using prefetched objects.

        Args:
            pairs: Iterable of (entity_type, entity_id) tuples.
            include_hierarchy (bool): Return full hierarchy path when True.
            localized (bool): Use localized country names when True.
            prefetched (dict, optional): Pre-loaded {(entity_type, entity_id): model} map.

        Returns:
            dict: Mapping of (entity_type, entity_id) -> name string.
        """
        normalized_pairs = []
        for entity_type, entity_id in pairs or []:
            normalized = EntityService._normalize_entity_pair(entity_type, entity_id)
            if normalized:
                normalized_pairs.append(normalized)

        if prefetched is None:
            prefetched = EntityService.prefetch_entities(
                normalized_pairs,
                include_hierarchy=include_hierarchy,
            )

        names = {}
        for pair in normalized_pairs:
            entity = prefetched.get(pair)
            if entity:
                names[pair] = EntityService._name_from_entity(
                    pair[0], entity, include_hierarchy=include_hierarchy, localized=localized,
                )
            else:
                entity_type, entity_id = pair
                if include_hierarchy:
                    names[pair] = f"Unknown {entity_type}"
                else:
                    names[pair] = f"Unknown {entity_type} (ID: {entity_id})"
        return names

    @staticmethod
    def attach_display_names(
        entity_rows,
        *,
        include_hierarchy=True,
        localized=True,
        key="display_name",
    ):
        """Add display names to dicts that include ``entity_type`` and ``entity_id`` keys."""
        if not entity_rows:
            return {}
        pairs = [
            (row.get("entity_type"), row.get("entity_id"))
            for row in entity_rows
            if row.get("entity_type") is not None and row.get("entity_id") is not None
        ]
        names = EntityService.batch_entity_names(
            pairs,
            include_hierarchy=include_hierarchy,
            localized=localized,
        )
        for row in entity_rows:
            et = row.get("entity_type")
            eid = row.get("entity_id")
            if et is None or eid is None:
                continue
            normalized = EntityService._normalize_entity_pair(et, eid)
            row[key] = names.get(normalized, "") if normalized else ""
        return names

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
        return EntityService._localized_hierarchy_from_entity(entity_type, entity)

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
        return EntityService._hierarchy_from_entity(entity_type, entity)

    @staticmethod
    def get_country_from_entity(entity_type, entity):
        """Get the related country from an already-loaded entity object."""
        if not entity:
            return None

        if entity_type == EntityType.country.value:
            return entity

        if entity_type == EntityType.ns_branch.value:
            return entity.country if hasattr(entity, 'country') else None
        if entity_type == EntityType.ns_subbranch.value:
            return entity.branch.country if (hasattr(entity, 'branch') and entity.branch) else None
        if entity_type == EntityType.ns_localunit.value:
            return entity.branch.country if (hasattr(entity, 'branch') and entity.branch) else None

        if entity_type in [
            EntityType.division.value,
            EntityType.department.value,
            EntityType.regional_office.value,
            EntityType.cluster_office.value,
        ]:
            return None

        return None

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
        return EntityService.get_country_from_entity(entity_type, entity)

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
        from app.services.organization.authorization_service import AuthorizationService
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

        pairs = [(perm.entity_type, perm.entity_id) for perm in permissions]
        prefetched = EntityService.prefetch_entities(pairs, include_hierarchy=False)

        entities = []
        for perm in permissions:
            entity = prefetched.get((perm.entity_type, perm.entity_id))
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
        from app.services.organization.authorization_service import AuthorizationService
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
