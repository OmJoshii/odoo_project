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
    
    # ── Helper: Convert book record to dict ──────────────────
    def _book_to_dict(self, book):
        """
        Converts a library.book record into a
        plain dictionary safe for JSON serialization.
        Always use this when returning book data.
        """
        return {
            'id': book.id,
            'name': book.name,
            'author': book.author_id.name
                      if book.author_id else None,
            'author_id': book.author_id.id
                         if book.author_id else None,
            'author_nationality': book.author_nationality
                                  or None,
            'isbn': book.isbn or None,
            'pages': book.pages or 0,
            'price': book.price,
            'state': book.state,
            'is_available': book.is_available,
            'available_copies': book.available_copies,
            'total_copies': book.copy_count,
            'date_published': str(book.date_published)
                              if book.date_published
                              else None,
            'description': book.description or None,
            'categories': [
                {'id': cat.id, 'name': cat.name}
                for cat in book.category_ids
            ],
            'has_cover': bool(book.cover_image),
            'cover_url': f'/web/image/library.book/'
                         f'{book.id}/cover_image'
                         if book.cover_image else None,
        }
    
    # First Endpoint: List all Books
    @http.route(
        '/api/library/books',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def api_get_books(self, **kwargs):
        """
        GET /api/library/books
        GET /api/library/books?state=available
        GET /api/library/books?search=harry
        GET /api/library/books?page=1&limit=10

        Returns a list of books with optional filtering.
        Requires X-API-Key header.
        """
        # Step 1 — Validate API key
        if not self._validate_key():
            return self._unauthorized()

        # Step 2 — Read query parameters
        state = kwargs.get('state')
        search = kwargs.get('search')
        page = int(kwargs.get('page', 1))
        limit = int(kwargs.get('limit', 20))

        # Step 3 — Build domain
        domain = []
        if state:
            valid_states = ['available', 'borrowed', 'lost']
            if state not in valid_states:
                return self._bad_request(
                    f'Invalid state. Must be one of: '
                    f'{", ".join(valid_states)}'
                )
            domain.append(('state', '=', state))

        if search:
            domain.append('|')
            domain.append(('name', 'ilike', search))
            domain.append(('author_id.name', 'ilike', search))

        # Step 4 — Calculate pagination
        offset = (page - 1) * limit

        # Step 5 — Fetch books from database
        books = request.env['library.book'].sudo().search(
            domain,
            limit=limit,
            offset=offset,
            order='name asc',
        )
        total = request.env['library.book'].sudo().search_count(
            domain
        )

        # Step 6 — Convert to list of dicts
        books_data = [self._book_to_dict(book) for book in books]

        # Step 7 — Return response
        return self._json_response({
            'status': 'success',
            'code': 200,
            'page': page,
            'limit': limit,
            'total': total,
            'pages': (total + limit - 1) // limit,
            'data': books_data,
        })
    
    # Second Endpoint: Get One Book

    @http.route(
        '/api/library/books/<int:book_id>',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def api_get_book(self, book_id, **kwargs):
        """
        GET /api/library/books/1

        Returns full details of one specific book.
        Requires X-API-Key header.
        """
        # Step 1 — Validate API key
        if not self._validate_key():
            return self._unauthorized()

        # Step 2 — Fetch the book
        book = request.env['library.book'].sudo().browse(book_id)

        # Step 3 — Check it exists
        if not book.exists():
            return self._not_found(
                f'Book with ID {book_id} not found'
            )

        # Step 4 — Return full book data
        return self._json_response({
            'status': 'success',
            'code': 200,
            'data': self._book_to_dict(book),
        })
    
    # Stats Endpoint
    @http.route(
        '/api/library/stats',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def api_get_stats(self, **kwargs):
        """
        GET /api/library/stats

        Returns library statistics — total books,
        available, borrowed, members, requests.
        Requires X-API-Key header.
        """
        # Step 1 — Validate API key
        if not self._validate_key():
            return self._unauthorized()

        # Step 2 — Gather stats
        Book = request.env['library.book'].sudo()
        Request = request.env['library.borrow.request'].sudo()
        Member = request.env['res.partner'].sudo()

        total_books = Book.search_count([])
        available_books = Book.search_count([
            ('state', '=', 'available')
        ])
        borrowed_books = Book.search_count([
            ('state', '=', 'borrowed')
        ])
        total_members = Member.search_count([
            ('is_library_member', '=', True)
        ])
        pending_requests = Request.search_count([
            ('state', '=', 'pending')
        ])
        active_borrows = Request.search_count([
            ('state', '=', 'approved')
        ])

        # Step 3 — Return stats
        return self._json_response({
            'status': 'success',
            'code': 200,
            'data': {
                'books': {
                    'total': total_books,
                    'available': available_books,
                    'borrowed': borrowed_books,
                    'lost': total_books - available_books
                            - borrowed_books,
                },
                'members': {
                    'total': total_members,
                },
                'requests': {
                    'pending': pending_requests,
                    'active_borrows': active_borrows,
                },
            }
        })