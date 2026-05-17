from odoo import models, fields, api
from odoo.exceptions import ValidationError


class LibraryBorrowWizard(models.TransientModel):
    _name = 'library.borrow.wizard'
    _description = 'Borrow Book Wizard'

    # The book being borrowed
    book_id = fields.Many2one(
        comodel_name='library.book',
        string='Book',
        required=True,
        readonly=True,
    )

    # Who is borrowing
    member_id = fields.Many2one(
        comodel_name='res.partner',
        string='Member',
        required=True,
        domain="[('is_library_member', '=', True)]",
    )

    # When it should be returned
    borrow_date = fields.Date(
        string='Borrow Date',
        default=fields.Date.today,
        required=True,
    )
    return_date = fields.Date(
        string='Expected Return Date',
        required=True,
    )

    notes = fields.Text(string='Notes')

    # ── Constraints ──────────────────────────────────────────
    @api.constrains('borrow_date', 'return_date')
    def _check_dates(self):
        for rec in self:
            if rec.return_date <= rec.borrow_date:
                raise ValidationError(
                    'Return date must be after borrow date!'
                )

    @api.constrains('book_id')
    def _check_book_available(self):
        for rec in self:
            if rec.book_id.state != 'available':
                raise ValidationError(
                    f'Book "{rec.book_id.name}" is not '
                    f'available for borrowing!'
                )

    # ── Onchange ─────────────────────────────────────────────
    @api.onchange('borrow_date')
    def _onchange_borrow_date(self):
        if self.borrow_date:
            # Default return date = 14 days after borrow
            from datetime import timedelta
            self.return_date = (
                self.borrow_date + timedelta(days=14)
            )

    # ── Action method ────────────────────────────────────────
    def action_confirm_borrow(self):
        self.ensure_one()
        self.book_id.write({
            'state': 'borrowed',
            'is_available': False,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Book Borrowed!',
                'message': (
                    f'"{self.book_id.name}" has been borrowed '
                    f'by {self.member_id.name}. '
                    f'Return by {self.return_date}'
                ),
                'type': 'success',
                'sticky': False,
            }
        }