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