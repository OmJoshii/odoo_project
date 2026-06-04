from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class LibraryWaitlist(models.Model):
    _name = 'library.waitlist'
    _description = 'Library Book Waitlist'
    _order = 'book_id, position asc'

    # ── Fields ───────────────────────────────────────────────
    book_id = fields.Many2one(
        comodel_name='library.book',
        string='Book',
        required=True,
        ondelete='cascade',
    )
    name = fields.Char(
        string='Requester Name',
        required=True,
    )
    email = fields.Char(
        string='Requester Email',
        required=True,
    )
    phone = fields.Char(
        string='Phone (Optional)',
    )
    position = fields.Integer(
        string='Queue Position',
        readonly=True,
    )
    state = fields.Selection([
        ('waiting', 'Waiting'),
        ('notified', 'Notified'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='waiting')

    request_date = fields.Datetime(
        string='Requested On',
        default=fields.Datetime.now,
        readonly=True,
    )
    notified_date = fields.Datetime(
        string='Notified On',
        readonly=True,
    )

    # ── Auto assign position ──────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'position' not in vals or not vals['position']:
                # Get the next position for this book
                book_id = vals.get('book_id')
                if book_id:
                    last = self.search([
                        ('book_id', '=', book_id),
                        ('state', 'in',
                         ['waiting', 'notified']),
                    ], order='position desc', limit=1)
                    vals['position'] = (
                        last.position + 1 if last else 1
                    )
        return super().create(vals_list)

    # ── Constraints ──────────────────────────────────────────
    @api.constrains('book_id', 'email')
    def _check_duplicate(self):
        for rec in self:
            existing = self.search([
                ('book_id', '=', rec.book_id.id),
                ('email', '=', rec.email),
                ('state', 'in', ['waiting', 'notified']),
                ('id', '!=', rec.id),
            ])
            if existing:
                raise ValidationError(
                    f'You are already on the waitlist '
                    f'for "{rec.book_id.name}" at '
                    f'position {existing[0].position}.'
                )

    # ── Actions ──────────────────────────────────────────────
    def action_cancel(self):
        self.ensure_one()
        self.write({'state': 'cancelled'})
        # Reorder remaining positions
        self._reorder_positions()

    def action_mark_fulfilled(self):
        self.ensure_one()
        self.write({'state': 'fulfilled'})

    def _reorder_positions(self):
        """
        Reorders queue positions after a cancellation
        so there are no gaps in the numbering.
        """
        waiting = self.search([
            ('book_id', '=', self.book_id.id),
            ('state', 'in', ['waiting', 'notified']),
        ], order='position asc')

        for i, entry in enumerate(waiting, start=1):
            if entry.position != i:
                entry.position = i

    # ── Notify first in queue ─────────────────────────────────
    @api.model
    def notify_next_in_queue(self, book_id):
        """
        Called when a book becomes available.
        Finds the first waiting person and emails them.
        """
        next_entry = self.search([
            ('book_id', '=', book_id),
            ('state', '=', 'waiting'),
        ], order='position asc', limit=1)

        if not next_entry:
            _logger.info(
                'No one on waitlist for book ID %d',
                book_id
            )
            return

        # Send notification email
        template = self.env.ref(
            'library_management'
            '.email_template_waitlist_notification',
            raise_if_not_found=False,
        )

        if template:
            try:
                template.send_mail(
                    next_entry.id,
                    force_send=True,
                )
                next_entry.write({
                    'state': 'notified',
                    'notified_date': fields.Datetime.now(),
                })
                _logger.info(
                    'Waitlist notification sent to %s '
                    'for book ID %d',
                    next_entry.email, book_id,
                )
            except Exception as e:
                _logger.error(
                    'Failed to send waitlist email: %s',
                    str(e)
                )
        else:
            _logger.warning(
                'Waitlist email template not found'
            )