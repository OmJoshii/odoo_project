from odoo import models, fields, api
from odoo.exceptions import ValidationError


class LibraryBorrowRequest(models.Model):
    _name = 'library.borrow.request'
    _description = 'Library Borrow Request'
    _order = 'create_date desc'

    # ── Fields ───────────────────────────────────────────────
    name = fields.Char(
        string='Request Reference',
        readonly=True,
        default='New',
    )
    borrower_name = fields.Char(
        string='Borrower Name',
        required=True,
    )
    borrower_email = fields.Char(
        string='Borrower Email',
        required=True,
    )
    book_id = fields.Many2one(
        comodel_name='library.book',
        string='Book',
        required=True,
        ondelete='cascade',
    )
    borrow_date = fields.Date(
        string='Borrow Date',
        required=True,
    )
    return_date = fields.Date(
        string='Return Date',
        required=True,
    )
    state = fields.Selection([
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('returned', 'Returned'),
        ('rejected', 'Rejected'),
    ], string='Status', default='pending')

    notes = fields.Text(string='Notes')

    # ── Auto generate reference number ───────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'library.borrow.request'
                ) or 'New'
        return super().create(vals_list)

    # ── Constraints ──────────────────────────────────────────
    @api.constrains('borrow_date', 'return_date')
    def _check_dates(self):
        for rec in self:
            if rec.return_date <= rec.borrow_date:
                raise ValidationError(
                    'Return date must be after borrow date!'
                )

    # ── Actions ──────────────────────────────────────────────
    def action_approve(self):
        self.ensure_one()
        self.book_id.write({
            'state': 'borrowed',
            'is_available': False,
        })
        self.write({'state': 'approved'})

    def action_reject(self):
        self.ensure_one()
        self.write({'state': 'rejected'})

    def action_return(self):
        self.ensure_one()
        self.book_id.write({
            'state': 'available',
            'is_available': True,
        })
        self.write({'state': 'returned'})