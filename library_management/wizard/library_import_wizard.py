from odoo import models, fields, api
from odoo.exceptions import ValidationError
import base64
import io
import csv
import logging

_logger = logging.getLogger(__name__)


class LibraryImportWizard(models.TransientModel):
    _name = 'library.import.wizard'
    _description = 'Import Books from CSV'

    # ── Fields ───────────────────────────────────────────────
    csv_file = fields.Binary(
        string='CSV File',
        required=True,
        help='Upload a CSV file with columns: '
             'name, author, isbn, pages, price, '
             'date_published, description'
    )
    csv_filename = fields.Char(string='Filename')

    # Results shown after import
    state = fields.Selection([
        ('draft', 'Ready to Import'),
        ('done', 'Import Complete'),
    ], default='draft')

    total_rows = fields.Integer(
        string='Total Rows', readonly=True
    )
    success_count = fields.Integer(
        string='Successfully Imported', readonly=True
    )
    error_count = fields.Integer(
        string='Errors', readonly=True
    )
    error_log = fields.Text(
        string='Error Details', readonly=True
    )
    imported_ids = fields.Many2many(
        comodel_name='library.book',
        string='Imported Books',
        readonly=True,
    )

    # ── Download sample CSV ───────────────────────────────────
    def action_download_sample(self):
        """
        Generates and downloads a sample CSV file
        so librarians know the exact format needed.
        """
        sample_data = (
            'name,author,isbn,pages,price,'
            'date_published,description,'
            'categories,cover_image_url\n'
            'Harry Potter,J.K. Rowling,'
            '9780439708180,309,500.00,'
            '1997-06-26,A young wizard,'
            '"Fiction,Fantasy",'
            'https://covers.openlibrary.org/b/isbn/9780439708180-L.jpg\n'
            'The Da Vinci Code,Dan Brown,'
            '0385504209,454,600.00,'
            '2003-03-18,A murder mystery,'
            'Thriller,'
            'https://covers.openlibrary.org/b/isbn/0385504209-L.jpg\n'
        )

        # Encode as base64 for download
        sample_bytes = sample_data.encode('utf-8')
        sample_b64 = base64.b64encode(sample_bytes)

        # Create an attachment the user can download
        attachment = self.env['ir.attachment'].create({
            'name': 'sample_books_import.csv',
            'type': 'binary',
            'datas': sample_b64,
            'mimetype': 'text/csv',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}'
                   f'?download=true',
            'target': 'self',
        }

    # ── Main import method ────────────────────────────────────
    def action_import(self):
        """
        Reads the uploaded CSV and creates
        library.book records for each valid row.
        """
        self.ensure_one()

        if not self.csv_file:
            raise ValidationError(
                'Please upload a CSV file first.'
            )

        # Verify it's a CSV file
        if self.csv_filename and not \
                self.csv_filename.lower().endswith('.csv'):
            raise ValidationError(
                'Only CSV files are supported. '
                'Please upload a .csv file.'
            )

        # Step 1 — Decode the uploaded file
        try:
            csv_data = base64.b64decode(self.csv_file)
            csv_text = csv_data.decode('utf-8')
        except Exception:
            # Try latin-1 encoding if utf-8 fails
            try:
                csv_text = csv_data.decode('latin-1')
            except Exception:
                raise ValidationError(
                    'Could not read the file. '
                    'Please ensure it is a valid CSV.'
                )

        # Step 2 — Parse CSV
        try:
            reader = csv.DictReader(
                io.StringIO(csv_text),
                skipinitialspace=True,
            )
            rows = list(reader)
        except Exception as e:
            raise ValidationError(
                f'Could not parse CSV: {str(e)}'
            )

        if not rows:
            raise ValidationError(
                'The CSV file is empty or has no data rows.'
            )

        # Step 3 — Validate required columns exist
        required_columns = ['name']
        if reader.fieldnames:
            fieldnames_lower = [
                f.strip().lower()
                for f in reader.fieldnames
            ]
            for col in required_columns:
                if col not in fieldnames_lower:
                    raise ValidationError(
                        f'Required column "{col}" not found. '
                        f'Found columns: '
                        f'{", ".join(reader.fieldnames)}'
                    )

        # Step 4 — Process each row
        success_count = 0
        error_count = 0
        errors = []
        imported_books = self.env['library.book']

        for row_num, row in enumerate(rows, start=2):
            try:
                book = self._process_row(row, row_num)
                if book:
                    imported_books |= book
                    success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f'Row {row_num}: {str(e)}')
                _logger.warning(
                    'CSV import row %d error: %s',
                    row_num, str(e)
                )

        # Step 5 — Update wizard with results
        error_log = '\n'.join(errors) if errors else 'None'
        self.write({
            'state': 'done',
            'total_rows': len(rows),
            'success_count': success_count,
            'error_count': error_count,
            'error_log': error_log,
            'imported_ids': [(6, 0, imported_books.ids)],
        })

        _logger.info(
            'CSV Import complete: %d success, %d errors',
            success_count, error_count,
        )

        # Step 6 — Return updated wizard view
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'library.import.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ── Row processor ─────────────────────────────────────────
    def _process_row(self, row, row_num):
        """
        Processes one CSV row and creates a book.
        Returns the created book record.
        Raises an exception if the row is invalid.
        """
        # Clean all values — strip whitespace
        cleaned = {
            k.strip().lower(): v.strip()
            for k, v in row.items()
            if k
        }

        # Validate name — required
        name = cleaned.get('name', '')
        if not name:
            raise ValueError(
                'Book title (name) is required'
            )

        # Build values dictionary
        vals = {'name': name}

        # Handle author — find or create
        author_name = cleaned.get('author', '')
        if author_name:
            author = self.env[
                'library.author'
            ].search([
                ('name', '=', author_name)
            ], limit=1)
            if not author:
                author = self.env[
                    'library.author'
                ].create({'name': author_name})
            vals['author_id'] = author.id

        # Handle ISBN — check for duplicates
        isbn = cleaned.get('isbn', '')
        if isbn:
            existing = self.env['library.book'].search([
                ('isbn', '=', isbn)
            ], limit=1)
            if existing:
                raise ValueError(
                    f'ISBN {isbn} already exists '
                    f'(book: "{existing.name}")'
                )
            vals['isbn'] = isbn

        # Handle pages — must be a positive integer
        pages_str = cleaned.get('pages', '')
        if pages_str:
            try:
                pages = int(pages_str)
                if pages < 0:
                    raise ValueError('Pages cannot be negative')
                vals['pages'] = pages
            except ValueError as e:
                if 'negative' in str(e):
                    raise
                raise ValueError(
                    f'Pages must be a number, got: {pages_str}'
                )

        # Handle price — must be a positive float
        price_str = cleaned.get('price', '')
        if price_str:
            try:
                price = float(price_str)
                if price < 0:
                    raise ValueError('Price cannot be negative')
                vals['price'] = price
            except ValueError as e:
                if 'negative' in str(e):
                    raise
                raise ValueError(
                    f'Price must be a number, got: {price_str}'
                )

        # Handle date_published
        date_str = cleaned.get('date_published', '')
        if date_str:
            from datetime import date
            try:
                date.fromisoformat(date_str)
                vals['date_published'] = date_str
            except ValueError:
                raise ValueError(
                    f'Date must be YYYY-MM-DD, '
                    f'got: {date_str}'
                )

        # Handle description
        description = cleaned.get('description', '')
        if description:
            vals['description'] = description

        # Handle categories — comma separated values
        categories_str = cleaned.get('categories', '')
        if categories_str:
            category_ids = []
            # Split by comma and clean each category name
            category_names = [
                c.strip()
                for c in categories_str.split(',')
                if c.strip()
            ]
            for cat_name in category_names:
                # Find existing category or create new one
                category = self.env[
                    'library.category'
                ].search([
                    ('name', '=', cat_name)
                ], limit=1)
                if not category:
                    category = self.env[
                        'library.category'
                    ].create({'name': cat_name})
                category_ids.append(category.id)

            if category_ids:
                # Many2many write syntax
                vals['category_ids'] = [(6, 0, category_ids)]
            
            # Handle cover_image_url
            cover_url = cleaned.get('cover_image_url', '')
            if cover_url:
                try:
                    import urllib.request
                    import base64 as b64

                    # Set a browser-like User-Agent header
                    # Some servers block Python's default agent
                    req = urllib.request.Request(
                        cover_url,
                        headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }
                    )

                    # Download the image with 10 second timeout
                    with urllib.request.urlopen(
                        req, timeout=10
                    ) as response:
                        image_data = response.read()

                    # Convert to base64 for Odoo image field
                    vals['cover_image'] = b64.b64encode(
                        image_data
                    ).decode('utf-8')

                except Exception as e:
                    # Don't fail the whole import if image fails
                    # Just log a warning and continue
                    _logger.warning(
                        'Row %d: Could not download image '
                        'from %s — %s',
                        row_num, cover_url, str(e)
                    )
        # Create the book
        return self.env['library.book'].create(vals)

    # ── View imported books ───────────────────────────────────
    def action_view_imported_books(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Imported Books',
            'res_model': 'library.book',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.imported_ids.ids)],
        }