from odoo import models, fields, api
from odoo.exceptions import ValidationError

class LibraryMember(models.Model):
    # Type 1 inheritance — extending res.partner
    # No _name needed — we are adding to the existing model
    _inherit = 'res.partner'

    # New fields added to res.partner
    is_library_member = fields.Boolean(
        string='Library Member',
        default=False,
    )
    library_card_number = fields.Char(
        string='Library Card Number',
    )
    membership_start = fields.Date(
        string='Membership Start Date',
    )
    membership_end = fields.Date(
        string='Membership End Date',
    )
    membership_status = fields.Selection([
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('suspended', 'Suspended'),
    ], string='Membership Status', default='active')

    # Computed field — is membership currently valid?
    is_membership_valid = fields.Boolean(
        string='Membership Valid',
        compute='_compute_is_membership_valid',
        store=True,
    )

    @api.depends('membership_end', 'membership_status')
    def _compute_is_membership_valid(self):
        today = fields.Date.today()
        for rec in self:
            if (rec.membership_status == 'active' and
                    rec.membership_end and
                    rec.membership_end >= today):
                rec.is_membership_valid = True
            else:
                rec.is_membership_valid = False

    @api.constrains('membership_start', 'membership_end')
    def _check_membership_dates(self):
        for rec in self:
            if (rec.membership_start and rec.membership_end and
                    rec.membership_start > rec.membership_end):
                raise ValidationError(
                    'Membership end date must be after start date!'
                )
            
    
    # ── Scheduled Action Methods ─────────────────────────────
    @api.model
    def action_expire_memberships(self):
        """
        Runs daily — finds all active memberships
        whose end date has passed and marks them expired.
        """
        today = fields.Date.today()
        expired = self.search([
            ('is_library_member', '=', True),
            ('membership_status', '=', 'active'),
            ('membership_end', '<', today),
        ])
        if expired:
            expired.write({'membership_status': 'expired'})

        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(
            'Library cron: %d membership(s) expired on %s',
            len(expired),
            today,
        )
        return True