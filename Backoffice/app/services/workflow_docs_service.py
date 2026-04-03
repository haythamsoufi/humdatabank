"""
Workflow Documentation Service

Handles loading, parsing, and querying workflow documentation for the chatbot.
Workflow docs are structured markdown files that describe step-by-step processes
and can be converted to interactive tour configurations.
"""

import os
import re
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from flask import current_app

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    """Represents a single step in a workflow."""
    step_number: int
    title: str
    page: str
    selector: str
    help_text: str
    action: Optional[str] = None
    action_text: Optional[str] = None
    fields: Optional[List[Dict[str, str]]] = None


@dataclass
class WorkflowDoc:
    """Represents a parsed workflow document."""
    id: str
    title: str
    description: str
    roles: List[str]
    category: str
    pages: List[str]
    keywords: List[str] = field(default_factory=list)
    content: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    tips: List[str] = field(default_factory=list)
    file_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'roles': self.roles,
            'category': self.category,
            'pages': self.pages,
            'keywords': self.keywords,
            'steps': [
                {
                    'step_number': s.step_number,
                    'title': s.title,
                    'page': s.page,
                    'selector': s.selector,
                    'help': s.help_text,
                    'action': s.action,
                    'actionText': s.action_text,
                    'fields': s.fields
                }
                for s in self.steps
            ],
            'prerequisites': self.prerequisites,
            'tips': self.tips
        }

    def to_tour_config(self) -> Dict[str, Any]:
        """Convert to InteractiveTour.js configuration format."""
        return {
            'name': self.title,
            'steps': [
                {
                    'page': step.page,
                    'selector': step.selector,
                    'help': f"Step {step.step_number} of {len(self.steps)}: {step.help_text}",
                    'actionText': step.action_text or 'Next'
                }
                for step in self.steps
            ]
        }


class WorkflowDocsService:
    """
    Service for loading, parsing, and querying workflow documentation.

    Features:
    - Load workflow markdown files with YAML frontmatter
    - Parse steps into structured tour configurations
    - Search workflows by query and filter by user role
    - Generate embeddings for semantic search via the RAG system
    - Multi-language support with fallback to English
    """

    # Supported languages for workflow translations
    SUPPORTED_LANGUAGES = {'en', 'fr', 'es', 'ar'}

    # Regex patterns for parsing markdown
    FRONTMATTER_PATTERN = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)
    STEP_HEADER_PATTERN = re.compile(r'^###\s+Step\s+(\d+):\s*(.+)$', re.MULTILINE)
    FIELD_PATTERN = re.compile(r'^\s*-\s+\*\*(.+?)\*\*:\s*(.+)$', re.MULTILINE)
    LIST_ITEM_PATTERN = re.compile(r'^\s*-\s+(.+)$', re.MULTILINE)

    def __init__(self, workflows_dir: Optional[str] = None):
        """Initialize the workflow documentation service."""
        if workflows_dir:
            self.workflows_dir = Path(workflows_dir)
        else:
            # Default to docs/workflows relative to Backoffice root
            base_dir = Path(current_app.root_path).parent
            self.workflows_dir = base_dir / 'docs' / 'workflows'

        self._workflows_cache: Dict[str, WorkflowDoc] = {}
        # Cache for translated workflows: (workflow_id, language) -> WorkflowDoc
        self._translations_cache: Dict[tuple, WorkflowDoc] = {}
        self._loaded = False

    def _ensure_loaded(self):
        """Ensure workflows are loaded into cache."""
        if not self._loaded:
            self.load_all_workflows()

    def _normalize_language(self, language: Optional[str]) -> str:
        """Normalize language code to supported value."""
        if not language or not isinstance(language, str):
            return 'en'
        lang = language.strip().lower()[:2]
        return lang if lang in self.SUPPORTED_LANGUAGES else 'en'

    def _get_translation_path(self, base_path: Path, language: str) -> Optional[Path]:
        """
        Get the path to a translation file for a given language.

        Args:
            base_path: Path to the English (default) workflow file
            language: Target language code (e.g., 'fr', 'ar', 'es')

        Returns:
            Path to translation file if it exists, None otherwise
        """
        if language == 'en':
            return base_path

        # Convert add-user.md -> add-user.fr.md
        stem = base_path.stem
        translated_path = base_path.parent / f"{stem}.{language}.md"

        if translated_path.exists():
            return translated_path
        return None

    def _get_workflow_translated(self, workflow_id: str, language: str) -> Optional[WorkflowDoc]:
        """
        Get a workflow in a specific language, with fallback to English.

        Args:
            workflow_id: The workflow identifier
            language: Target language code

        Returns:
            WorkflowDoc in requested language, or English fallback
        """
        language = self._normalize_language(language)
        cache_key = (workflow_id, language)

        # Check translation cache first
        if cache_key in self._translations_cache:
            return self._translations_cache[cache_key]

        # Get the base English workflow
        self._ensure_loaded()
        base_workflow = self._workflows_cache.get(workflow_id)
        if not base_workflow:
            return None

        # If requesting English, return base workflow
        if language == 'en':
            return base_workflow

        # Try to find and parse the translation file
        base_path = Path(base_workflow.file_path)
        translation_path = self._get_translation_path(base_path, language)

        if translation_path and translation_path != base_path:
            try:
                translated_workflow = self._parse_workflow_file(translation_path)
                if translated_workflow:
                    # Ensure the translated workflow keeps the same ID
                    translated_workflow.id = workflow_id
                    self._translations_cache[cache_key] = translated_workflow
                    return translated_workflow
            except Exception as e:
                logger.debug("Translation cache/load failed: %s", e)

        # Fallback to English
        return base_workflow

    def load_all_workflows(self) -> List[WorkflowDoc]:
        """
        Load all workflow markdown files from the workflows directory.

        Returns:
            List of parsed WorkflowDoc objects
        """
        self._workflows_cache.clear()
        workflows = []

        if not self.workflows_dir.exists():
            logger.warning(f"Workflows directory does not exist: {self.workflows_dir}")
            self._loaded = True
            return workflows

        # Walk through all subdirectories
        for root, dirs, files in os.walk(self.workflows_dir):
            # Skip schema file
            for filename in files:
                if filename.endswith('.md') and not filename.startswith('_'):
                    file_path = Path(root) / filename
                    # Skip translation files (they have language suffix like .fr.md, .es.md, .ar.md)
                    # These are loaded on-demand in _get_workflow_translated
                    if any(file_path.stem.endswith(f'.{lang}') for lang in self.SUPPORTED_LANGUAGES if lang != 'en'):
                        continue

                    try:
                        workflow = self._parse_workflow_file(file_path)
                        if workflow:
                            self._workflows_cache[workflow.id] = workflow
                            workflows.append(workflow)
                    except Exception as e:
                        logger.warning(f"Failed to parse workflow file {file_path}: {e}", exc_info=True)

        self._loaded = True
        return workflows

    def _parse_workflow_file(self, file_path: Path) -> Optional[WorkflowDoc]:
        """
        Parse a single workflow markdown file.

        Args:
            file_path: Path to the markdown file

        Returns:
            WorkflowDoc object or None if parsing fails
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return None

        # Parse YAML frontmatter
        frontmatter_match = self.FRONTMATTER_PATTERN.match(content)
        if not frontmatter_match:
            return None

        try:
            frontmatter = yaml.safe_load(frontmatter_match.group(1))
        except yaml.YAMLError as e:
            return None

        # Validate required fields
        required_fields = ['id', 'title', 'description', 'roles', 'category', 'pages']
        for field in required_fields:
            if field not in frontmatter:
                return None

        # Extract body content (after frontmatter)
        body_content = content[frontmatter_match.end():]

        # Parse steps from body
        steps = self._parse_steps(body_content)

        # Parse prerequisites
        prerequisites = self._parse_section_list(body_content, 'Prerequisites')

        # Parse tips
        tips = self._parse_section_list(body_content, 'Tips')

        return WorkflowDoc(
            id=frontmatter['id'],
            title=frontmatter['title'],
            description=frontmatter['description'],
            roles=frontmatter['roles'] if isinstance(frontmatter['roles'], list) else [frontmatter['roles']],
            category=frontmatter['category'],
            pages=frontmatter['pages'] if isinstance(frontmatter['pages'], list) else [frontmatter['pages']],
            keywords=frontmatter.get('keywords', []),
            content=body_content,
            steps=steps,
            prerequisites=prerequisites,
            tips=tips,
            file_path=str(file_path)
        )

    def _parse_steps(self, content: str) -> List[WorkflowStep]:
        """Parse workflow steps from markdown content."""
        steps = []

        # Split content by step headers
        step_matches = list(self.STEP_HEADER_PATTERN.finditer(content))

        for i, match in enumerate(step_matches):
            step_number = int(match.group(1))
            step_title = match.group(2).strip()

            # Get content until next step or end
            start_pos = match.end()
            end_pos = step_matches[i + 1].start() if i + 1 < len(step_matches) else len(content)
            step_content = content[start_pos:end_pos]

            # Parse step fields
            page = self._extract_field(step_content, 'Page')
            selector = self._extract_field(step_content, 'Selector')
            help_text = self._extract_field(step_content, 'Help')
            action = self._extract_field(step_content, 'Action')
            action_text = self._extract_field(step_content, 'ActionText')

            # Parse fields list if present
            fields = self._parse_fields_list(step_content)

            if page and selector and help_text:
                steps.append(WorkflowStep(
                    step_number=step_number,
                    title=step_title,
                    page=page,
                    selector=selector,
                    help_text=help_text,
                    action=action,
                    action_text=action_text,
                    fields=fields
                ))

        return steps

    def _extract_field(self, content: str, field_name: str) -> Optional[str]:
        """Extract a field value from markdown content."""
        pattern = rf'^\s*-\s+\*\*{field_name}\*\*:\s*(.+?)(?:\n|$)'
        match = re.search(pattern, content, re.MULTILINE)
        if match:
            value = match.group(1).strip()
            # Remove markdown code formatting if present
            if value.startswith('`') and value.endswith('`'):
                value = value[1:-1]
            return value
        return None

    def _parse_fields_list(self, content: str) -> Optional[List[Dict[str, str]]]:
        """Parse the Fields list from step content."""
        # Find the Fields section
        fields_match = re.search(r'-\s+\*\*Fields\*\*:\s*\n((?:\s+-\s+.+\n?)+)', content)
        if not fields_match:
            return None

        fields = []
        fields_content = fields_match.group(1)

        # Parse each field line
        for line in fields_content.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                # Parse "Field Name (required): Description" format
                field_match = re.match(r'-\s+(.+?)(?:\s+\((\w+)\))?:\s*(.+)', line)
                if field_match:
                    fields.append({
                        'name': field_match.group(1).strip(),
                        'required': field_match.group(2) == 'required' if field_match.group(2) else False,
                        'description': field_match.group(3).strip()
                    })

        return fields if fields else None

    def _parse_section_list(self, content: str, section_name: str) -> List[str]:
        """Parse a bullet list from a named section."""
        # Find section header
        pattern = rf'##\s+{section_name}\s*\n((?:[-*]\s+.+\n?)+)'
        match = re.search(pattern, content, re.MULTILINE)
        if not match:
            return []

        items = []
        for line in match.group(1).split('\n'):
            line = line.strip()
            if line.startswith('-') or line.startswith('*'):
                items.append(line[1:].strip())

        return items

    def get_workflow_by_id(self, workflow_id: str) -> Optional[WorkflowDoc]:
        """
        Get a specific workflow by ID.

        Args:
            workflow_id: The unique workflow identifier

        Returns:
            WorkflowDoc or None if not found
        """
        self._ensure_loaded()
        return self._workflows_cache.get(workflow_id)

    def get_all_workflows(self) -> List[WorkflowDoc]:
        """
        Get all loaded workflows.

        Returns:
            List of all WorkflowDoc objects
        """
        self._ensure_loaded()
        return list(self._workflows_cache.values())

    def get_workflows_for_role(self, role: str) -> List[WorkflowDoc]:
        """
        Get workflows accessible to a specific role.

        Args:
            role: User role ('admin' or 'focal_point')

        Returns:
            List of WorkflowDoc objects accessible to the role
        """
        self._ensure_loaded()
        return [
            w for w in self._workflows_cache.values()
            if role in w.roles or 'all' in w.roles
        ]

    def search_workflows(
        self,
        query: str,
        role: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[WorkflowDoc]:
        """
        Search workflows by query text and filter by role/category.

        This is a simple keyword-based search. For semantic search,
        use the vector store integration.

        Args:
            query: Search query string
            role: Optional role filter
            category: Optional category filter

        Returns:
            List of matching WorkflowDoc objects, sorted by relevance
        """
        self._ensure_loaded()

        query_lower = query.lower()
        query_words = set(query_lower.split())

        results = []

        for workflow in self._workflows_cache.values():
            # Apply role filter
            if role and role not in workflow.roles and 'all' not in workflow.roles:
                continue

            # Apply category filter
            if category and workflow.category != category:
                continue

            # Calculate relevance score
            score = 0

            # Check title
            if query_lower in workflow.title.lower():
                score += 10

            # Check keywords
            for keyword in workflow.keywords:
                if keyword.lower() in query_lower or query_lower in keyword.lower():
                    score += 5

            # Check description
            if query_lower in workflow.description.lower():
                score += 3

            # Check individual words
            for word in query_words:
                if len(word) < 3:
                    continue
                if word in workflow.title.lower():
                    score += 2
                if word in workflow.description.lower():
                    score += 1
                if any(word in kw.lower() for kw in workflow.keywords):
                    score += 2

            if score > 0:
                results.append((score, workflow))

        # Sort by score descending
        results.sort(key=lambda x: x[0], reverse=True)

        return [workflow for score, workflow in results]

    def get_workflow_for_tour(self, workflow_id: str, language: str = 'en') -> Optional[Dict[str, Any]]:
        """
        Get workflow data formatted for tour registration.

        Args:
            workflow_id: The workflow identifier
            language: Target language code (en, fr, es, ar). Defaults to 'en'.

        Returns:
            Tour configuration dict or None
        """
        language = self._normalize_language(language)
        workflow = self._get_workflow_translated(workflow_id, language)

        if not workflow or not workflow.steps:
            return None

        tour_config = workflow.to_tour_config()
        # Add language info to the response
        tour_config['language'] = language
        return tour_config

    def get_workflow_summary(self, workflow_id: str) -> Optional[str]:
        """
        Get a brief summary of a workflow for chatbot responses.

        Args:
            workflow_id: The workflow identifier

        Returns:
            Summary string or None
        """
        workflow = self.get_workflow_by_id(workflow_id)
        if not workflow:
            return None

        summary = f"**{workflow.title}**\n\n{workflow.description}\n\n"

        if workflow.prerequisites:
            summary += "**Prerequisites:**\n"
            for prereq in workflow.prerequisites:
                summary += f"- {prereq}\n"
            summary += "\n"

        summary += "**Steps:**\n"
        for step in workflow.steps:
            summary += f"{step.step_number}. {step.title}\n"

        if workflow.tips:
            summary += "\n**Tips:**\n"
            for tip in workflow.tips[:3]:  # Limit to 3 tips
                summary += f"- {tip}\n"

        return summary

    def format_workflow_for_llm(self, workflow: WorkflowDoc) -> str:
        """
        Format a workflow document for inclusion in LLM context.

        Args:
            workflow: The workflow document

        Returns:
            Formatted string for LLM context
        """
        text = f"# Workflow: {workflow.title}\n"
        text += f"ID: {workflow.id}\n"
        text += f"Category: {workflow.category}\n"
        text += f"Roles: {', '.join(workflow.roles)}\n"
        text += f"Pages: {', '.join(workflow.pages)}\n\n"
        text += f"Description: {workflow.description}\n\n"

        if workflow.prerequisites:
            text += "Prerequisites:\n"
            for prereq in workflow.prerequisites:
                text += f"- {prereq}\n"
            text += "\n"

        text += "Steps:\n"
        for step in workflow.steps:
            text += f"\nStep {step.step_number}: {step.title}\n"
            text += f"- Page: {step.page}\n"
            text += f"- Selector: {step.selector}\n"
            text += f"- Help: {step.help_text}\n"
            if step.action:
                text += f"- Action: {step.action}\n"
            if step.action_text:
                text += f"- ActionText: {step.action_text}\n"
            if step.fields:
                text += "- Fields:\n"
                for field in step.fields:
                    req = " (required)" if field.get('required') else ""
                    text += f"  - {field['name']}{req}: {field['description']}\n"

        if workflow.tips:
            text += "\nTips:\n"
            for tip in workflow.tips:
                text += f"- {tip}\n"

        return text

    def get_all_workflow_text_for_embedding(self) -> List[Dict[str, Any]]:
        """
        Get all workflows formatted for embedding/vector store.

        Returns:
            List of dicts with 'id', 'text', and 'metadata' keys
        """
        self._ensure_loaded()

        results = []
        for workflow in self._workflows_cache.values():
            results.append({
                'id': f"workflow:{workflow.id}",
                'text': self.format_workflow_for_llm(workflow),
                'metadata': {
                    'type': 'workflow',
                    'workflow_id': workflow.id,
                    'title': workflow.title,
                    'category': workflow.category,
                    'roles': workflow.roles,
                    'pages': workflow.pages,
                    'keywords': workflow.keywords
                }
            })

        return results

    def reload(self):
        """Force reload all workflow documents."""
        self._loaded = False
        self._workflows_cache.clear()
        self._translations_cache.clear()
        self.load_all_workflows()

    def sync_to_vector_store(self) -> Dict[str, Any]:
        """
        Sync all workflow documents to the RAG vector store.

        Creates or updates AIDocument and related embeddings for each workflow.

        Returns:
            Dict with sync results including counts and any errors
        """
        from app.extensions import db
        from app.models import AIDocument, AIDocumentChunk, AIEmbedding
        from app.services.ai_embedding_service import AIEmbeddingService
        from app.services.ai_vector_store import AIVectorStore
        from app.services.ai_chunking_service import AIChunkingService
        from app.utils.datetime_helpers import utcnow

        self._ensure_loaded()

        results = {
            'synced': 0,
            'updated': 0,
            'errors': [],
            'total_cost': 0.0
        }

        embedder = AIEmbeddingService()
        vector_store = AIVectorStore()
        chunker = AIChunkingService()

        for workflow in self._workflows_cache.values():
            try:
                # Check if document already exists
                doc_title = f"Workflow: {workflow.title}"
                existing = AIDocument.query.filter_by(
                    title=doc_title,
                    file_type='workflow'
                ).first()

                # Format content for embedding
                content = self.format_workflow_for_llm(workflow)

                if existing:
                    # Update existing document
                    doc = existing
                    doc.updated_at = utcnow()

                    # Remove old chunks and embeddings
                    AIDocumentChunk.query.filter_by(document_id=doc.id).delete()
                    AIEmbedding.query.filter_by(document_id=doc.id).delete()
                    doc.total_chunks = 0
                    doc.total_embeddings = 0

                    results['updated'] += 1
                else:
                    # Create new document
                    doc = AIDocument(
                        title=doc_title,
                        filename=f"{workflow.id}.md",
                        file_type='workflow',
                        processing_status='processing',
                        is_public=True,
                        searchable=True,
                        extra_metadata={
                            'workflow_id': workflow.id,
                            'category': workflow.category,
                            'roles': workflow.roles,
                            'pages': workflow.pages,
                            'keywords': workflow.keywords
                        }
                    )
                    db.session.add(doc)
                    db.session.flush()  # Get the ID

                    results['synced'] += 1

                # Create chunks (workflow docs are typically small, so usually 1 chunk)
                chunks_data = chunker.chunk_document(
                    text=content,
                    strategy='semantic'
                )

                chunk_objects = []
                for i, chunk_data in enumerate(chunks_data):
                    chunk = AIDocumentChunk(
                        document_id=doc.id,
                        chunk_index=i,
                        content=chunk_data.content,
                        content_length=chunk_data.char_count,
                        token_count=chunk_data.token_count,
                        chunk_type='workflow',
                        extra_metadata={
                            'workflow_id': workflow.id,
                            'category': workflow.category,
                            'roles': workflow.roles
                        }
                    )
                    db.session.add(chunk)
                    chunk_objects.append(chunk)

                db.session.flush()  # Get chunk IDs

                # Generate embeddings
                texts = [c.content for c in chunk_objects]
                embeddings, costs = embedder.embed_documents(texts)

                total_cost = sum(costs)
                results['total_cost'] += total_cost

                # Store embeddings
                chunks_with_embeddings = [
                    (chunk_objects[i], embeddings[i], costs[i])
                    for i in range(len(chunk_objects))
                ]
                vector_store.store_document_embeddings(doc.id, chunks_with_embeddings)

                # Update document status
                doc.processing_status = 'completed'
                doc.processed_at = utcnow()
                doc.total_chunks = len(chunk_objects)
                doc.total_tokens = sum(c.token_count for c in chunk_objects)
                doc.embedding_model = embedder.model
                doc.embedding_dimensions = embedder.dimensions

                db.session.commit()

            except Exception as e:
                db.session.rollback()
                error_msg = f"Error syncing workflow {workflow.id}."
                results['errors'].append(error_msg)

        return results

    def search_in_vector_store(
        self,
        query: str,
        role: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search workflow documents using vector similarity.

        Args:
            query: Search query
            role: Optional role filter
            limit: Maximum results to return

        Returns:
            List of matching workflow chunks with scores
        """
        from app.services.ai_vector_store import AIVectorStore

        vector_store = AIVectorStore()

        filters = {'file_type': 'workflow'}
        if role and str(role).strip():
            filters['workflow_role'] = str(role).strip()

        try:
            results = vector_store.search_similar(
                query_text=query,
                top_k=limit * 2,
                filters=filters,
            )

            # Restrict to workflow chunks and apply limit
            filtered = [
                r for r in results
                if (r.get('metadata') or {}).get('chunk_type') == 'workflow'
            ]
            return filtered[:limit]

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
