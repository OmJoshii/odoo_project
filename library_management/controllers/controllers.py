from odoo import http, fields
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class LibraryWebsiteController(http.Controller):

    @http.route('/library', type='http', auth='public', website=True)
    def library_home(self, book_filter=None, **kwargs):
        """
        Public catalogue page — shows all books
        with live counts and filter support
        """
        # Always fetch ALL books for counts
        all_books = request.env['library.book'].sudo().search([])

        # Calculate live counts
        total_books = len(all_books)
        total_available = len(all_books.filtered(
            lambda b: b.state == 'available'
        ))
        total_borrowed = len(all_books.filtered(
            lambda b: b.state == 'borrowed'
        ))

        # Apply filter for display
        if book_filter == 'available':
            books = all_books.filtered(
                lambda b: b.state == 'available'
            )
            active_filter = 'available'
        elif book_filter == 'borrowed':
            books = all_books.filtered(
                lambda b: b.state == 'borrowed'
            )
            active_filter = 'borrowed'
        else:
            books = all_books
            active_filter = 'all'

        return request.render(
            'library_management.template_library_home',
            {
                'books': books,
                'total_books': total_books,
                'total_available': total_available,
                'total_borrowed': total_borrowed,
                'active_filter': active_filter,
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
