from odoo import models, fields, api
from odoo.exceptions import ValidationError


class LibraryBook(models.Model):
    _name = 'library.book'
    _description = 'Library Book'

    name = fields.Char(string='Title', required=True)

    # Many2one — many books link to one author
    author_id = fields.Many2one(
        comodel_name='library.author',
        string='Author',
        ondelete='set null',
    )

    # Many2many — many books link to many categories
    category_ids = fields.Many2many(
        comodel_name='library.category',
        relation='library_book_category_rel',
        column1='book_id',
        column2='category_id',
        string='Categories'
    )

    isbn = fields.Char(string='ISBN')
    pages = fields.Integer(string='Number of Pages')
    price = fields.Float(string='Price')
    is_available = fields.Boolean(string='Is Available', default=True)
    date_published = fields.Date(string='Published Date')
    description = fields.Text(string='Description')

    # ── Cover image ──────────────────────────────────────────
    cover_image = fields.Image(
        string='Cover Image',
        max_width=800,
        max_height=1200,
    )
    cover_image_small = fields.Image(
        string='Cover Image (Small)',
        related='cover_image',
        max_width=128,
        max_height=128,
        store=True,
    )
    state = fields.Selection([
        ('available', 'Available'),
        ('borrowed', 'Borrowed'),
        ('lost', 'Lost'),
    ], string='Status',
       compute='_compute_state',
       store=True,
       readonly=False,
       default='available')

    # ── Computed field ──────────────────────────────────────
    author_nationality = fields.Char(
        string='Author Nationality',
        compute='_compute_author_nationality',
        store=True,
    )

    short_description = fields.Char(
        string='Short Description',
        compute='_compute_short_description',
        store=False,
    )

    # ── Copy tracking fields ─────────────────────────────────
    copy_count = fields.Integer(
        string='Total Copies',
        default=1,
        help='Total number of physical copies in the library'
    )
    borrowed_count = fields.Integer(
        string='Borrowed Copies',
        compute='_compute_borrowed_count',
        store=True,
    )
    available_copies = fields.Integer(
        string='Available Copies',
        compute='_compute_available_copies',
        store=True,
    )
    borrow_request_ids = fields.One2many(
        comodel_name='library.borrow.request',
        inverse_name='book_id',
        string='Borrow Requests',
    )

    # ── SQL Constraints ──────────────────────────────────────
    _sql_constraints = [
        (
            'unique_isbn',
            'UNIQUE(isbn)',
            'A book with this ISBN already exists!'
        ),
        (
            'positive_price',
            'CHECK(price >= 0)',
            'Price cannot be negative!'
        ),
        (
            'positive_pages',
            'CHECK(pages >= 0)',
            'Number of pages cannot be negative!'
        ),
    ]

    # ── Compute methods ─────────────────────────────────────
    @api.depends('author_id', 'author_id.nationality')
    def _compute_author_nationality(self):
        for rec in self:
            if rec.author_id and rec.author_id.nationality:
                rec.author_nationality = rec.author_id.nationality
            else:
                rec.author_nationality = 'Unknown'

    @api.depends('description')
    def _compute_short_description(self):
        for rec in self:
            if rec.description:
                rec.short_description = rec.description[:80] + '...'
            else:
                rec.short_description = 'No description available'

    # ── Onchange method ──────────────────────────────────────
    """@api.onchange('state')
    def _onchange_state(self):
        if self.state == 'borrowed':
            self.is_available = False
        elif self.state == 'available':
            self.is_available = True
        elif self.state == 'lost':
            self.is_available = False"""
    
    @api.depends('available_copies', 'copy_count')
    def _compute_state(self):
        for rec in self:
            if rec.copy_count <= 0:
                rec.state = 'lost'
            elif rec.available_copies > 0:
                rec.state = 'available'
            else:
                rec.state = 'borrowed'

    @api.depends('borrow_request_ids.state')
    def _compute_borrowed_count(self):
        for rec in self:
            rec.borrowed_count = self.env[
                'library.borrow.request'
            ].search_count([
                ('book_id', '=', rec.id),
                ('state', '=', 'approved'),
            ])

    @api.depends('copy_count', 'borrowed_count')
    def _compute_available_copies(self):
        for rec in self:
            rec.available_copies = max(
                0, rec.copy_count - rec.borrowed_count
            )

    
    # ── Python Constraints ───────────────────────────────────
    @api.constrains('isbn')
    def _check_isbn(self):
        for rec in self:
            if rec.isbn and len(rec.isbn) not in [10, 13]:
                raise ValidationError(
                    f'ISBN must be 10 or 13 characters long. '
                    f'You entered {len(rec.isbn)} characters.'
                )

    @api.constrains('date_published')
    def _check_date_published(self):
        for rec in self:
            if rec.date_published and rec.date_published > fields.Date.today():
                raise ValidationError(
                    'Published date cannot be in the future!'
                )

    @api.constrains('price', 'pages')
    def _check_price_and_pages(self):
        for rec in self:
            if rec.price < 0:
                raise ValidationError('Price cannot be negative!')
            if rec.pages < 0:
                raise ValidationError(
                    'Number of pages cannot be negative!'
                )
            

    # ── Wizard button methods ────────────────────────────────
    def action_open_borrow_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Borrow Book',
            'res_model': 'library.borrow.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_book_id': self.id,
            },
        }

    def action_return_book(self):
        self.ensure_one()
        self.write({
            'state': 'available',
            'is_available': True,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Book Returned!',
                'message': f'"{self.name}" is now available.',
                'type': 'success',
                'sticky': False,
            }
        }
    
    # ── Scheduled Action Methods ─────────────────────────────
    @api.model
    def action_check_overdue_books(self):
        today = fields.Date.today()
        import logging
        _logger = logging.getLogger(__name__)

        # Find all approved requests past return date
        overdue_requests = self.env[
            'library.borrow.request'
        ].search([
            ('state', '=', 'approved'),
            ('return_date', '<', today),
        ])

        # Trigger fine recompute on each overdue request
        for req in overdue_requests:
            req._compute_fine()

        _logger.info(
            'Library cron: %d overdue request(s) '
            'found and fines updated on %s',
            len(overdue_requests),
            today,
        )
        return True 
    
    def action_print_report(self):
        self.ensure_one()
        return self.env.ref(
            'library_management.action_report_library_book'
        ).report_action(self)
    
    borrow_request_count = fields.Integer(
        string='Borrow Requests',
        compute='_compute_borrow_request_count',
    )

    @api.depends('borrow_request_ids')
    def _compute_borrow_request_count(self):
        for rec in self:
            rec.borrow_request_count = self.env[
                'library.borrow.request'
            ].search_count([('book_id', '=', rec.id)])

    def action_view_borrow_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Borrow Requests',
            'res_model': 'library.borrow.request',
            'view_mode': 'list,form',
            'domain': [('book_id', '=', self.id)],
        }