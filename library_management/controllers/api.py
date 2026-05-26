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
    
    # ── Helper: Convert borrow request to dict ────────────────
    def _request_to_dict(self, req):
        """
        Converts a library.borrow.request record
        into a plain dictionary for JSON response.
        """
        return {
            'id': req.id,
            'reference': req.name,
            'borrower_name': req.borrower_name,
            'borrower_email': req.borrower_email,
            'book': {
                'id': req.book_id.id,
                'name': req.book_id.name,
                'author': req.book_id.author_id.name
                          if req.book_id.author_id
                          else None,
            },
            'borrow_date': str(req.borrow_date)
                           if req.borrow_date else None,
            'return_date': str(req.return_date)
                           if req.return_date else None,
            'state': req.state,
            'overdue_days': req.overdue_days,
            'fine_amount': req.fine_amount,
            'fine_paid': req.fine_paid,
            'created_on': str(req.create_date)
                          if req.create_date else None,
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
    
    # POST borrow request endpoint
    @http.route(
        '/api/library/borrow',
        type='http',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def api_create_borrow(self, **kwargs):
        """
        POST /api/library/borrow

        Submits a new borrow request.
        Requires X-API-Key header.
        Requires JSON body with:
          - book_id (integer)
          - borrower_name (string)
          - borrower_email (string)
          - borrow_date (string: YYYY-MM-DD)
          - return_date (string: YYYY-MM-DD)
        """
        # Step 1 — Validate API key
        if not self._validate_key():
            return self._unauthorized()

        # Step 2 — Read JSON body
        try:
            body = json.loads(
                request.httprequest.data.decode('utf-8')
            )
        except (json.JSONDecodeError, Exception):
            return self._bad_request(
                'Request body must be valid JSON'
            )

        # Step 3 — Extract and validate required fields
        book_id = body.get('book_id')
        borrower_name = body.get('borrower_name', '').strip()
        borrower_email = body.get('borrower_email', '').strip()
        borrow_date = body.get('borrow_date')
        return_date = body.get('return_date')

        # Check all required fields present
        missing = []
        if not book_id:
            missing.append('book_id')
        if not borrower_name:
            missing.append('borrower_name')
        if not borrower_email:
            missing.append('borrower_email')
        if not borrow_date:
            missing.append('borrow_date')
        if not return_date:
            missing.append('return_date')

        if missing:
            return self._bad_request(
                f'Missing required fields: '
                f'{", ".join(missing)}'
            )

        # Validate email format
        if '@' not in borrower_email:
            return self._bad_request(
                'Invalid email address format'
            )

        # Step 4 — Validate dates
        from datetime import date
        try:
            borrow = date.fromisoformat(borrow_date)
            ret = date.fromisoformat(return_date)
        except ValueError:
            return self._bad_request(
                'Dates must be in YYYY-MM-DD format'
            )

        if ret <= borrow:
            return self._bad_request(
                'Return date must be after borrow date'
            )

        # Step 5 — Check book exists and is available
        book = request.env[
            'library.book'
        ].sudo().browse(int(book_id))

        if not book.exists():
            return self._not_found(
                f'Book with ID {book_id} not found'
            )

        if book.available_copies <= 0:
            return self._json_response({
                'status': 'error',
                'code': 409,
                'message': f'No copies of "{book.name}" '
                           f'are available for borrowing',
            }, status=409)

        # Step 6 — Create the borrow request
        try:
            borrow_request = request.env[
                'library.borrow.request'
            ].sudo().create({
                'book_id': int(book_id),
                'borrower_name': borrower_name,
                'borrower_email': borrower_email,
                'borrow_date': borrow_date,
                'return_date': return_date,
            })
        except Exception as e:
            _logger.error(
                'API borrow request creation failed: %s',
                str(e)
            )
            return self._json_response({
                'status': 'error',
                'code': 500,
                'message': 'Failed to create borrow request. '
                           'Please try again.',
            }, status=500)

        # Step 7 — Return success response
        return self._json_response({
            'status': 'success',
            'code': 201,
            'message': f'Borrow request submitted successfully. '
                       f'Reference: {borrow_request.name}',
            'data': self._request_to_dict(borrow_request),
        }, status=201)
    
    # GET requests by email endpoint
    @http.route(
        '/api/library/requests',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def api_get_requests(self, **kwargs):
        """
        GET /api/library/requests?email=om@example.com
        GET /api/library/requests?email=x&state=pending

        Returns borrow requests for a given email.
        Requires X-API-Key header.
        """
        # Step 1 — Validate API key
        if not self._validate_key():
            return self._unauthorized()

        # Step 2 — Get and validate email parameter
        email = kwargs.get('email', '').strip()
        state = kwargs.get('state')

        if not email:
            return self._bad_request(
                'email parameter is required. '
                'Use ?email=your@email.com'
            )

        if '@' not in email:
            return self._bad_request(
                'Invalid email address format'
            )

        # Step 3 — Build domain
        domain = [('borrower_email', '=', email)]

        if state:
            valid_states = [
                'pending', 'approved',
                'returned', 'rejected'
            ]
            if state not in valid_states:
                return self._bad_request(
                    f'Invalid state. Must be one of: '
                    f'{", ".join(valid_states)}'
                )
            domain.append(('state', '=', state))

        # Step 4 — Fetch requests
        requests_records = request.env[
            'library.borrow.request'
        ].sudo().search(
            domain,
            order='create_date desc',
        )

        # Step 5 — Return response
        return self._json_response({
            'status': 'success',
            'code': 200,
            'email': email,
            'total': len(requests_records),
            'data': [
                self._request_to_dict(r)
                for r in requests_records
            ],
        })
    
    # GET single request endpoint
    @http.route(
        '/api/library/requests/detail',
        type='http',
        auth='none',
        methods=['GET'],
        csrf=False,
    )
    def api_get_request(self, **kwargs):
        """
        GET /api/library/requests/detail?ref=BRW/0001

        Returns details of one specific borrow request.
        Requires X-API-Key header.
        """
        

        if not self._validate_key():
            return self._unauthorized()

        # Read reference from query parameter
        reference = kwargs.get('ref', '').strip()

        if not reference:
            return self._bad_request(
                'ref parameter is required. '
                'Use ?ref=BRW/0001'
            )

        # Find by reference number
        borrow_request = request.env[
            'library.borrow.request'
        ].sudo().search([
            ('name', '=', reference)
        ], limit=1)

        if not borrow_request:
            return self._not_found(
                f'Request with reference '
                f'"{reference}" not found'
            )

        return self._json_response({
            'status': 'success',
            'code': 200,
            'data': self._request_to_dict(borrow_request),
        })