from odoo import http
from odoo.http import request, Response
import json
import logging

_logger = logging.getLogger(__name__)


class LibraryApiController(http.Controller):
    """
    REST API Controller for Library Management Module.
    Base URL: /api/library/
    Authentication: X-API-Key header required on all endpoints
    """

    # ── Helper: Build standard JSON response ─────────────────
    def _json_response(self, data, status=200):
        """
        Returns a properly formatted JSON response.
        Always use this instead of returning raw dicts.
        """
        return Response(
            json.dumps(data),
            status=status,
            mimetype='application/json',
            headers={
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
            }
        )

    # ── Helper: Validate API key from request header ──────────
    def _validate_key(self):
        """
        Reads X-API-Key from request headers and validates it.
        Returns True if valid, False if not.
        """
        api_key = request.httprequest.headers.get('X-API-Key')
        if not api_key:
            return False
        return request.env['library.api.key'].sudo().validate_api_key(
            api_key
        )

    # ── Helper: Unauthorized response ────────────────────────
    def _unauthorized(self):
        return self._json_response({
            'status': 'error',
            'code': 401,
            'message': 'Invalid or missing API key. '
                       'Include X-API-Key header.',
        }, status=401)

    # ── Helper: Not found response ────────────────────────────
    def _not_found(self, message='Record not found'):
        return self._json_response({
            'status': 'error',
            'code': 404,
            'message': message,
        }, status=404)

    # ── Helper: Bad request response ─────────────────────────
    def _bad_request(self, message='Invalid request data'):
        return self._json_response({
            'status': 'error',
            'code': 400,
            'message': message,
        }, status=400)