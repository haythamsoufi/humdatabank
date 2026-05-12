# -*- coding: utf-8 -*-
"""
Standardized JSON response helpers for the mobile API surface (``/api/mobile/v1``).

Every mobile route should use these helpers exclusively — do **not** mix with
``json_ok`` / ``json_error`` from ``api_responses.py``.

Response envelope
-----------------

Success::

    {"success": true, "data": {...}, "meta": {...}}

Paginated success::

    {"success": true, "data": [...], "meta": {"total": 42, "page": 1, ...}}

Error::

    {"success": false, "error": "message", "error_code": "VALIDATION_ERROR"}
"""
from __future__ import annotations

from flask import jsonify


# ---------------------------------------------------------------------------
# Success responses
# ---------------------------------------------------------------------------

def mobile_ok(data=None, meta=None, message=None, **extra):
    """
    Standard mobile success response (HTTP 200).

    :param data: Primary payload (dict, list, or scalar).
    :param meta: Optional metadata dict (pagination info, etc.).
    :param message: Optional human-readable message.
    :param extra: Additional top-level keys merged into the body.
    """
    body: dict = {'success': True}
    if data is not None:
        body['data'] = data
    if meta:
        body['meta'] = meta
    if message:
        body['message'] = message
    body.update(extra)
    return jsonify(body), 200


def mobile_created(data=None, message=None, **extra):
    """Mobile success response for resource creation (HTTP 201)."""
    body: dict = {'success': True}
    if data is not None:
        body['data'] = data
    if message:
        body['message'] = message
    body.update(extra)
    return jsonify(body), 201


def mobile_paginated(items, total, page, per_page):
    """
    Paginated mobile success response.

    Always returns ``data`` as a list and ``meta`` with pagination fields.
    """
    total_pages = -(-total // per_page) if per_page else 0
    return mobile_ok(
        data=items,
        meta={
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
        },
    )


# ---------------------------------------------------------------------------
# Error responses
# ---------------------------------------------------------------------------

def mobile_error(message, status=400, error_code=None, **extra):
    """
    Standard mobile error response.

    :param message: Human-readable error description.
    :param status: HTTP status code (default 400).
    :param error_code: Machine-readable error code (e.g. ``VALIDATION_ERROR``).
    :param extra: Additional keys merged into the body.
    """
    body: dict = {'success': False, 'error': message}
    if error_code:
        body['error_code'] = error_code
    body.update(extra)
    return jsonify(body), status


def mobile_bad_request(message='Invalid request.', error_code=None, **extra):
    """HTTP 400 convenience wrapper."""
    return mobile_error(message, 400, error_code=error_code, **extra)


def mobile_auth_error(message='Authentication required. Please log in.'):
    """HTTP 401 — invalid or missing credentials."""
    return mobile_error(message, 401, error_code='AUTH_REQUIRED')


def mobile_forbidden(message='Access denied.'):
    """HTTP 403 — authenticated but not authorized."""
    return mobile_error(message, 403, error_code='FORBIDDEN')


def mobile_not_found(message='Not found.'):
    """HTTP 404."""
    return mobile_error(message, 404, error_code='NOT_FOUND')


def mobile_server_error(message='An unexpected error occurred. Please try again.'):
    """HTTP 500 — generic server error (never leak internals)."""
    return mobile_error(message, 500, error_code='SERVER_ERROR')
