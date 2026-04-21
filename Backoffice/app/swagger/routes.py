"""
Swagger/OpenAPI documentation routes
"""
from flask import Blueprint, current_app, jsonify, render_template
from flask_login import login_required
from app.swagger.openapi_spec import get_openapi_spec
from app.utils.api_responses import json_error, json_ok, json_server_error

swagger_bp = Blueprint('swagger', __name__, url_prefix='/api-docs')


@swagger_bp.route('/')
@login_required
def swagger_ui():
    """
    Serve the Swagger UI interface.
    """
    # Validate spec can be generated before rendering
    try:
        spec = get_openapi_spec()
        current_app.logger.info(f"Swagger UI: OpenAPI spec generated successfully with {len(spec.get('paths', {}))} paths")
    except Exception as e:
        current_app.logger.error(f"Error generating OpenAPI spec for Swagger UI: {e}", exc_info=True)
        # Still render the template - let Swagger UI handle the error

    response = current_app.make_response(render_template('swagger/swagger_ui.html'))
    # Ensure proper content type
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response


@swagger_bp.route('/openapi.json')
@login_required
def openapi_json():
    """
    Serve the OpenAPI specification as JSON.
    """
    try:
        spec = get_openapi_spec()
        # Validate spec has required fields
        if 'openapi' not in spec:
            current_app.logger.error("OpenAPI spec missing 'openapi' field")
            return json_server_error("Invalid OpenAPI specification")
        if 'paths' not in spec:
            current_app.logger.error("OpenAPI spec missing 'paths' field")
            return json_server_error("Invalid OpenAPI specification")

        current_app.logger.debug(f"Serving OpenAPI spec with {len(spec.get('paths', {}))} paths")
        response = jsonify(spec)
        return response
    except Exception as e:
        current_app.logger.error(f"Error generating OpenAPI spec: {e}", exc_info=True)
        return json_server_error("Failed to generate API documentation")


@swagger_bp.route('/openapi.yaml')
@login_required
def openapi_yaml():
    """
    Serve the OpenAPI specification as YAML.
    """
    try:
        import yaml
        spec = get_openapi_spec()
        yaml_str = yaml.dump(spec, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return current_app.response_class(
            yaml_str,
            mimetype='application/x-yaml; charset=utf-8'
        )
    except ImportError:
        current_app.logger.warning("PyYAML not installed, YAML endpoint unavailable")
        return json_error("YAML format not available. Install PyYAML to enable.", 503)
    except Exception as e:
        current_app.logger.error(f"Error generating OpenAPI YAML: {e}", exc_info=True)
        return json_server_error("Failed to generate API documentation")


@swagger_bp.route('/test')
def test_spec():
    """
    Test endpoint to verify OpenAPI spec generation.
    """
    try:
        spec = get_openapi_spec()
        import json
        # Try to serialize to validate JSON
        json_str = json.dumps(spec)
        return json_ok(
            status="success",
            openapi_version=spec.get("openapi"),
            title=spec.get("info", {}).get("title"),
            version=spec.get("info", {}).get("version"),
            paths_count=len(spec.get("paths", {})),
            tags_count=len(spec.get("tags", [])),
            has_components="components" in spec,
            has_schemas="schemas" in spec.get("components", {}),
            has_security_schemes="securitySchemes" in spec.get("components", {}),
            has_responses="responses" in spec.get("components", {}),
            json_valid=True,
            sample_paths=list(spec.get("paths", {}).keys())[:5],
        )
    except Exception as e:
        current_app.logger.error(f"Error in test endpoint: {e}", exc_info=True)
        return json_server_error(
            "Failed to run test request.",
            status="error",
        )
