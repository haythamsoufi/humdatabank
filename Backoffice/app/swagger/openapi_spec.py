"""
OpenAPI 3.0 specification for the Databank REST API.
"""
import os

def get_openapi_spec():
    """
    Returns the OpenAPI 3.0 specification as a dictionary.
    """
    base_url = os.environ.get('API_BASE_URL', 'http://localhost:5000')
    api_version = 'v1'

    org_name = "NGO Databank"
    try:
        from flask import has_app_context
        if has_app_context():
            from app.utils.organization_helpers import get_org_name as _get_org_name
            org_name = _get_org_name()
    except Exception:
        pass

    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": f"{org_name} API",
            "description": f"Comprehensive REST API for the {org_name} system. Provides access to countries, indicators, templates, submissions, and more.",
            "version": "1.0.0",
            "contact": {
                "name": f"{org_name} API Support",
                "email": "support@example.com"
            },
            "license": {
                "name": "Proprietary",
                "url": "https://example.com"
            }
        },
        "servers": [
            {
                "url": f"{base_url}/api/{api_version}",
                "description": "Production server"
            },
            {
                "url": "http://localhost:5000/api/v1",
                "description": "Development server"
            }
        ],
        "tags": [
            {
                "name": "Authentication",
                "description": "API authentication endpoints"
            },
            {
                "name": "Countries",
                "description": "Country and period management"
            },
            {
                "name": "Indicators",
                "description": "Indicator bank, sectors, and subsectors"
            },
            {
                "name": "Templates",
                "description": "Form templates and form items"
            },
            {
                "name": "Data",
                "description": "Form data and submissions"
            },
            {
                "name": "Submissions",
                "description": "Public and assigned form submissions"
            },
            {
                "name": "Users",
                "description": "User management and profiles"
            },
            {
                "name": "Assignments",
                "description": "Form assignments and entity management"
            },
            {
                "name": "Resources",
                "description": "Resources and publications"
            },
            {
                "name": "Documents",
                "description": "Submitted documents and file uploads"
            },
            {
                "name": "Common",
                "description": "Common words and shared resources"
            },
            {
                "name": "Quiz",
                "description": "Quiz functionality"
            },
            {
                "name": "Variables",
                "description": "Variable resolution"
            }
        ],
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "API Key",
                    "description": "Database-managed API key provided as Bearer token in Authorization header"
                }
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "properties": {
                        "success": {
                            "type": "boolean",
                            "example": False
                        },
                        "error": {
                            "type": "string",
                            "example": "Error message"
                        },
                        "error_id": {
                            "type": "string",
                            "format": "uuid",
                            "example": "123e4567-e89b-12d3-a456-426614174000"
                        },
                        "message": {
                            "type": "string",
                            "example": "Detailed error message"
                        }
                    },
                    "required": ["success", "error"]
                },
                "Country": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "example": 1},
                        "name": {"type": "string", "example": "Afghanistan"},
                        "iso3": {"type": "string", "example": "AFG"},
                        "region": {"type": "string", "example": "Asia Pacific"},
                        "multilingual_names": {
                            "type": "object",
                            "description": "Country names in different languages"
                        },
                        "national_society": {
                            "type": "object",
                            "description": "Primary national society information"
                        }
                    }
                },
                "Indicator": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "definition": {"type": "string"},
                        "type": {"type": "string"},
                        "unit": {"type": "string"},
                        "sector": {"type": "object"},
                        "archived": {"type": "boolean"}
                    }
                },
                "Template": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "version": {"type": "integer"},
                        "is_active": {"type": "boolean"}
                    }
                },
                "Submission": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "template_id": {"type": "integer"},
                        "country_id": {"type": "integer"},
                        "submitted_at": {"type": "string", "format": "date-time"},
                        "status": {"type": "string"}
                    }
                },
                "Pagination": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer", "example": 1},
                        "per_page": {"type": "integer", "example": 20},
                        "total": {"type": "integer", "example": 100},
                        "pages": {"type": "integer", "example": 5}
                    }
                }
            },
            "parameters": {
                "PageParam": {
                    "name": "page",
                    "in": "query",
                    "description": "Page number (1-indexed)",
                    "required": False,
                    "schema": {"type": "integer", "minimum": 1, "default": 1}
                },
                "PerPageParam": {
                    "name": "per_page",
                    "in": "query",
                    "description": "Number of items per page",
                    "required": False,
                    "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20}
                },
                "LocaleParam": {
                    "name": "locale",
                    "in": "query",
                    "description": "Locale code for localized responses (en, fr, es, ar, zh, ru, hi)",
                    "required": False,
                    "schema": {"type": "string", "default": "en"}
                }
            },
            "responses": {
                "Unauthorized": {
                    "description": "Unauthorized - Invalid or missing API key",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                },
                "Forbidden": {
                    "description": "Forbidden - Insufficient permissions",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                },
                "NotFound": {
                    "description": "Resource not found",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                },
                "BadRequest": {
                    "description": "Bad request - Invalid parameters",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                },
                "ServerError": {
                    "description": "Internal server error",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                }
            }
        },
        "paths": {}
    }

    # Add paths from separate function
    spec["paths"] = get_api_paths()

    return spec


def get_api_paths():
    """
    Returns all API paths with their operations.
    """
    paths = {
        "/countrymap": {
            "get": {
                "tags": ["Countries"],
                "summary": "Get all countries",
                "description": "Retrieve a list of all countries with optional localization and pagination.",
                "operationId": "getCountries",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {"$ref": "#/components/parameters/LocaleParam"},
                    {"$ref": "#/components/parameters/PageParam"},
                    {"$ref": "#/components/parameters/PerPageParam"}
                ],
                "responses": {
                    "200": {
                        "description": "List of countries",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "countries": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Country"}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "500": {"$ref": "#/components/responses/ServerError"}
                }
            }
        },
        "/periods": {
            "get": {
                "tags": ["Countries"],
                "summary": "Get periods",
                "description": "Retrieve available periods for data reporting.",
                "operationId": "getPeriods",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "List of periods",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "periods": {"type": "array", "items": {"type": "string"}}
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/indicator-bank": {
            "get": {
                "tags": ["Indicators"],
                "summary": "Get indicator bank",
                "description": "Retrieve all indicators from the indicator bank with optional filtering.",
                "operationId": "getIndicatorBank",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "search",
                        "in": "query",
                        "description": "Search query for indicator name or definition",
                        "required": False,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "type",
                        "in": "query",
                        "description": "Filter by indicator type",
                        "required": False,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "sector",
                        "in": "query",
                        "description": "Filter by sector name",
                        "required": False,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "sub_sector",
                        "in": "query",
                        "description": "Filter by sub-sector name",
                        "required": False,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "emergency",
                        "in": "query",
                        "description": "Filter by emergency type",
                        "required": False,
                        "schema": {"type": "string"}
                    },
                    {
                        "name": "archived",
                        "in": "query",
                        "description": "Filter by archived status (true/false)",
                        "required": False,
                        "schema": {"type": "string", "enum": ["true", "false"]}
                    },
                    {"$ref": "#/components/parameters/LocaleParam"}
                ],
                "responses": {
                    "200": {
                        "description": "List of indicators",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "indicators": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Indicator"}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/indicator-bank/{indicator_id}": {
            "get": {
                "tags": ["Indicators"],
                "summary": "Get indicator by ID",
                "description": "Retrieve a specific indicator by its ID.",
                "operationId": "getIndicatorById",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "indicator_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"}
                    },
                    {"$ref": "#/components/parameters/LocaleParam"}
                ],
                "responses": {
                    "200": {
                        "description": "Indicator details",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "indicator": {"$ref": "#/components/schemas/Indicator"}
                                    }
                                }
                            }
                        }
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/sectors": {
            "get": {
                "tags": ["Indicators"],
                "summary": "Get sectors",
                "description": "Retrieve all active sectors.",
                "operationId": "getSectors",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "List of sectors",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "sectors": {"type": "array", "items": {"type": "object"}}
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/subsectors": {
            "get": {
                "tags": ["Indicators"],
                "summary": "Get subsectors",
                "description": "Retrieve all active subsectors, optionally filtered by sector.",
                "operationId": "getSubsectors",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "sector_id",
                        "in": "query",
                        "description": "Filter by sector ID",
                        "required": False,
                        "schema": {"type": "integer"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "List of subsectors",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "subsectors": {"type": "array", "items": {"type": "object"}}
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/sectors-subsectors": {
            "get": {
                "tags": ["Indicators"],
                "summary": "Get sectors with subsectors",
                "description": "Retrieve all sectors with their associated subsectors.",
                "operationId": "getSectorsSubsectors",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "Sectors with subsectors",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "sectors": {"type": "array", "items": {"type": "object"}}
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/templates": {
            "get": {
                "tags": ["Templates"],
                "summary": "Get templates",
                "description": "Retrieve all form templates with optional filtering.",
                "operationId": "getTemplates",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "active",
                        "in": "query",
                        "description": "Filter by active status",
                        "required": False,
                        "schema": {"type": "boolean"}
                    },
                    {"$ref": "#/components/parameters/PageParam"},
                    {"$ref": "#/components/parameters/PerPageParam"}
                ],
                "responses": {
                    "200": {
                        "description": "List of templates",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "templates": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Template"}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/templates/{template_id}": {
            "get": {
                "tags": ["Templates"],
                "summary": "Get template by ID",
                "description": "Retrieve a specific template with all its sections and items.",
                "operationId": "getTemplateById",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "template_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Template details",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "template": {"$ref": "#/components/schemas/Template"}
                                    }
                                }
                            }
                        }
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/templates/{template_id}/data": {
            "get": {
                "tags": ["Data"],
                "summary": "Get data by template",
                "description": "Retrieve form data submitted for a specific template.",
                "operationId": "getDataByTemplate",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "template_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"}
                    },
                    {"$ref": "#/components/parameters/PageParam"},
                    {"$ref": "#/components/parameters/PerPageParam"}
                ],
                "responses": {
                    "200": {
                        "description": "Form data for template",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "data": {"type": "array", "items": {"type": "object"}}
                                    }
                                }
                            }
                        }
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/data": {
            "get": {
                "tags": ["Data"],
                "summary": "Get form data",
                "description": "Retrieve form data with advanced filtering, sorting, and pagination.",
                "operationId": "getFormData",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "template_id",
                        "in": "query",
                        "description": "Filter by template ID",
                        "required": False,
                        "schema": {"type": "integer"}
                    },
                    {
                        "name": "country_id",
                        "in": "query",
                        "description": "Filter by country ID",
                        "required": False,
                        "schema": {"type": "integer"}
                    },
                    {
                        "name": "start_date",
                        "in": "query",
                        "description": "Start date (YYYY-MM-DD)",
                        "required": False,
                        "schema": {"type": "string", "format": "date"}
                    },
                    {
                        "name": "end_date",
                        "in": "query",
                        "description": "End date (YYYY-MM-DD)",
                        "required": False,
                        "schema": {"type": "string", "format": "date"}
                    },
                    {"$ref": "#/components/parameters/PageParam"},
                    {"$ref": "#/components/parameters/PerPageParam"}
                ],
                "responses": {
                    "200": {
                        "description": "Form data",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "data": {"type": "array", "items": {"type": "object"}},
                                        "pagination": {"$ref": "#/components/schemas/Pagination"}
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/submissions": {
            "get": {
                "tags": ["Submissions"],
                "summary": "Get submissions",
                "description": "Retrieve form submissions with optional filtering.",
                "operationId": "getSubmissions",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "template_id",
                        "in": "query",
                        "description": "Filter by template ID",
                        "required": False,
                        "schema": {"type": "integer"}
                    },
                    {
                        "name": "country_id",
                        "in": "query",
                        "description": "Filter by country ID",
                        "required": False,
                        "schema": {"type": "integer"}
                    },
                    {"$ref": "#/components/parameters/PageParam"},
                    {"$ref": "#/components/parameters/PerPageParam"}
                ],
                "responses": {
                    "200": {
                        "description": "List of submissions",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "submissions": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Submission"}
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/submissions/{submission_id}": {
            "get": {
                "tags": ["Submissions"],
                "summary": "Get submission by ID",
                "description": "Retrieve a specific submission with all its data.",
                "operationId": "getSubmissionById",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "submission_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "integer"}
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Submission details",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "submission": {"$ref": "#/components/schemas/Submission"}
                                    }
                                }
                            }
                        }
                    },
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/users": {
            "get": {
                "tags": ["Users"],
                "summary": "Get users",
                "description": "Retrieve a list of users (admin only).",
                "operationId": "getUsers",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {"$ref": "#/components/parameters/PageParam"},
                    {"$ref": "#/components/parameters/PerPageParam"}
                ],
                "responses": {
                    "200": {
                        "description": "List of users",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "users": {"type": "array", "items": {"type": "object"}}
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"}
                }
            }
        },
        "/user/profile": {
            "get": {
                "tags": ["Users"],
                "summary": "Get current user profile",
                "description": "Retrieve the authenticated user's profile information.",
                "operationId": "getUserProfile",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "User profile",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "user": {"type": "object"}
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            },
            "put": {
                "tags": ["Users"],
                "summary": "Update user profile",
                "description": "Update the authenticated user's profile information.",
                "operationId": "updateUserProfile",
                "security": [{"BearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "email": {"type": "string", "format": "email"},
                                    "language": {"type": "string"}
                                }
                            }
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Updated user profile",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "user": {"type": "object"}
                                    }
                                }
                            }
                        }
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/resources": {
            "get": {
                "tags": ["Resources"],
                "summary": "Get resources",
                "description": "Retrieve all published resources.",
                "operationId": "getResources",
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {"$ref": "#/components/parameters/LocaleParam"},
                    {"$ref": "#/components/parameters/PageParam"},
                    {"$ref": "#/components/parameters/PerPageParam"}
                ],
                "responses": {
                    "200": {
                        "description": "List of resources",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "resources": {"type": "array", "items": {"type": "object"}}
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        },
        "/common-words": {
            "get": {
                "tags": ["Common"],
                "summary": "Get common words",
                "description": "Retrieve common words used in the system.",
                "operationId": "getCommonWords",
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "List of common words",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean"},
                                        "common_words": {"type": "array", "items": {"type": "string"}}
                                    }
                                }
                            }
                        }
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"}
                }
            }
        }
    }

    return paths
