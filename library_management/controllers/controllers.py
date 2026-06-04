from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class LibraryWebsiteController(http.Controller):

    @http.route('/library', type='http', auth='public', website=True)
    def library_home(self, book_filter=None, search=None, **kwargs):
        """
        Public catalogue page — with search and filter support
        """
        # Build search domain
        domain = []
        if search:
            domain = [
                '|',
                ('name', 'ilike', search),
                ('author_id.name', 'ilike', search),
            ]

        # Fetch ALL books for counts (no search applied)
        all_books = request.env['library.book'].sudo().search([])

        # Calculate live counts from all books
        total_books = len(all_books)
        total_available = len(all_books.filtered(
            lambda b: b.state == 'available'
        ))
        total_borrowed = len(all_books.filtered(
            lambda b: b.state == 'borrowed'
        ))

        # Fetch books with search domain applied
        searched_books = request.env['library.book'].sudo().search(domain)

        # Apply filter on top of search results
        if book_filter == 'available':
            books = searched_books.filtered(
                lambda b: b.state == 'available'
            )
            active_filter = 'available'
        elif book_filter == 'borrowed':
            books = searched_books.filtered(
                lambda b: b.state == 'borrowed'
            )
            active_filter = 'borrowed'
        else:
            books = searched_books
            active_filter = 'all'

        return request.render(
            'library_management.template_library_home',
            {
                'books': books,
                'total_books': total_books,
                'total_available': total_available,
                'total_borrowed': total_borrowed,
                'active_filter': active_filter,
                'search': search or '',
                'search_count': len(books),
            }
        )

    @http.route(
        '/library/book/<int:book_id>',
        type='http',
        auth='public',
        website=True,
    )
    def library_book_detail(self, book_id, **kwargs):
        """
        Public detail page for a single book
        """
        book = request.env['library.book'].sudo().browse(book_id)
        if not book.exists():
            return request.not_found()
        return request.render(
            'library_management.template_library_book_detail',
            {'book': book}
        )
    
    # ── NEW: Borrow form page ─────────────────────────────────
    @http.route(
        '/library/borrow/<int:book_id>',
        type='http',
        auth='public',
        website=True,
    )
    def library_borrow_form(self, book_id, **kwargs):
        book = request.env['library.book'].sudo().browse(book_id)
        if not book.exists():
            return request.not_found()
        if book.state != 'available':
            return request.redirect('/library')

        # Check if pending request already exists
        existing = request.env[
            'library.borrow.request'
        ].sudo().search_count([
            ('book_id', '=', book_id),
            ('state', '=', 'pending'),
        ])

        return request.render(
            'library_management.template_library_borrow_form',
            {
                'book': book,
                'today': fields.Date.today(),
                'error': kwargs.get('error'),
                'has_pending': existing > 0,
            }
        )

    # ── NEW: Handle borrow form submission ────────────────────
    @http.route(
        '/library/borrow/submit',
        type='http',
        auth='public',
        website=True,
        methods=['POST'],
    )
    def library_borrow_submit(self, **kwargs):
        book_id = int(kwargs.get('book_id', 0))
        borrower_name = kwargs.get('borrower_name', '').strip()
        borrower_email = kwargs.get('borrower_email', '').strip()
        borrow_date = kwargs.get('borrow_date')
        return_date = kwargs.get('return_date')

        # Basic validation
        if not all([borrower_name, borrower_email,
                    borrow_date, return_date]):
            return request.redirect(
                f'/library/borrow/{book_id}?error=missing_fields'
            )

        # Email validation
        if '@' not in borrower_email:
            return request.redirect(
                f'/library/borrow/{book_id}?error=invalid_email'
            )

        book = request.env['library.book'].sudo().browse(book_id)
        if not book.exists() or book.state != 'available':
            return request.redirect('/library')

        try:
            # ONLY create the borrow request
            # Do NOT change book state here
            request.env['library.borrow.request'].sudo().create({
                'book_id': book_id,
                'borrower_name': borrower_name,
                'borrower_email': borrower_email,
                'borrow_date': borrow_date,
                'return_date': return_date,
            })

            # ← REMOVED: book.sudo().write({...})
            # Book state only changes when librarian approves

        except Exception as e:
            _logger.error('Borrow request failed: %s', str(e))
            return request.redirect(
                f'/library/borrow/{book_id}?error=server_error'
            )

        return request.redirect(
            f'/library/borrow/success?name={borrower_name}'
            f'&book={book.name}'
        )

    # ── NEW: Success page ─────────────────────────────────────
    @http.route(
        '/library/borrow/success',
        type='http',
        auth='public',
        website=True,
    )
    def library_borrow_success(self, **kwargs):
        """
        Success page shown after successful borrow
        """
        return request.render(
            'library_management.template_library_borrow_success',
            {
                'borrower_name': kwargs.get('name', 'Friend'),
                'book_name': kwargs.get('book', 'the book'),
            }
        )
    
    @http.route(
        '/library/waitlist/<int:book_id>',
        type='http',
        auth='public',
        website=True,
    )
    def library_waitlist_form(self, book_id, **kwargs):
        """
        Shows the waitlist signup form for a book.
        Only accessible when book is not available.
        """
        book = request.env[
            'library.book'
        ].sudo().browse(book_id)
        if not book.exists():
            return request.not_found()

        # If book is available redirect to borrow instead
        if book.state == 'available':
            return request.redirect(
                f'/library/book/{book_id}'
            )

        # Get current queue length
        queue_length = request.env[
            'library.waitlist'
        ].sudo().search_count([
            ('book_id', '=', book_id),
            ('state', 'in', ['waiting', 'notified']),
        ])

        return request.render(
            'library_management'
            '.template_library_waitlist_form',
            {
                'book': book,
                'queue_length': queue_length,
                'error': kwargs.get('error'),
            }
        )

    @http.route(
        '/library/waitlist/submit',
        type='http',
        auth='public',
        website=True,
        methods=['POST'],
    )
    def library_waitlist_submit(self, **kwargs):
        """
        Handles waitlist form submission.
        """
        book_id = int(kwargs.get('book_id', 0))
        name = kwargs.get('name', '').strip()
        email = kwargs.get('email', '').strip()
        phone = kwargs.get('phone', '').strip()

        # Validation
        if not all([book_id, name, email]):
            return request.redirect(
                f'/library/waitlist/{book_id}'
                f'?error=missing_fields'
            )

        if '@' not in email:
            return request.redirect(
                f'/library/waitlist/{book_id}'
                f'?error=invalid_email'
            )

        book = request.env[
            'library.book'
        ].sudo().browse(book_id)
        if not book.exists():
            return request.redirect('/library')

        # Check if already on waitlist
        existing = request.env[
            'library.waitlist'
        ].sudo().search_count([
            ('book_id', '=', book_id),
            ('email', '=', email),
            ('state', 'in', ['waiting', 'notified']),
        ])

        if existing:
            return request.redirect(
                f'/library/waitlist/{book_id}'
                f'?error=already_registered'
            )

        # Create waitlist entry
        try:
            entry = request.env[
                'library.waitlist'
            ].sudo().create({
                'book_id': book_id,
                'name': name,
                'email': email,
                'phone': phone,
            })
        except Exception:
            return request.redirect(
                f'/library/waitlist/{book_id}'
                f'?error=server_error'
            )

        return request.redirect(
            f'/library/waitlist/success'
            f'?name={name}'
            f'&book={book.name}'
            f'&position={entry.position}'
        )

    @http.route(
        '/library/waitlist/success',
        type='http',
        auth='public',
        website=True,
    )
    def library_waitlist_success(self, **kwargs):
        return request.render(
            'library_management'
            '.template_library_waitlist_success',
            {
                'name': kwargs.get('name', 'Friend'),
                'book_name': kwargs.get('book', 'the book'),
                'position': kwargs.get('position', '1'),
            }
        )
