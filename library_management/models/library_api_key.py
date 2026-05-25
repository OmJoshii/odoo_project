from odoo import models, fields, api
import secrets
import hashlib


class LibraryApiKey(models.Model):
    _name = 'library.api.key'
    _description = 'Library API Key'
    _order = 'create_date desc'

    name = fields.Char(
        string='Key Name',
        required=True,
        help='A label to identify this key e.g. "Mobile App"'
    )
    key_hash = fields.Char(
        string='Key Hash',
        readonly=True,
        help='Stored as a hash for security'
    )
    key_preview = fields.Char(
        string='Key Preview',
        readonly=True,
        help='First 8 characters so you can identify the key'
    )
    is_active = fields.Boolean(
        string='Active',
        default=True,
    )
    last_used = fields.Datetime(
        string='Last Used',
        readonly=True,
    )
    note = fields.Text(
        string='Notes',
        help='What app or person is this key for?'
    )

    # ── Generate key button ───────────────────────────────────
    def action_generate_key(self):
        self.ensure_one()
        # Generate a secure random key
        raw_key = secrets.token_hex(32)

        # Store only a hash of the key — never the raw key
        key_hash = hashlib.sha256(
            raw_key.encode()
        ).hexdigest()

        self.write({
            'key_hash': key_hash,
            'key_preview': raw_key[:8] + '...',
        })

        # Show the key to the user ONE TIME only
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'API Key Generated!',
                'message': f'Your API Key: {raw_key} — '
                           f'Copy it now, it will not be '
                           f'shown again!',
                'type': 'warning',
                'sticky': True,
            }
        }

    def action_deactivate(self):
        self.ensure_one()
        self.write({'is_active': False})

    # ── Class method to validate a key ───────────────────────
    @api.model
    def validate_api_key(self, raw_key):
        """
        Called on every API request.
        Returns True if key is valid, False otherwise.
        Also updates last_used timestamp.
        """
        if not raw_key:
            return False

        # Hash the incoming key and compare
        key_hash = hashlib.sha256(
            raw_key.encode()
        ).hexdigest()

        api_key = self.search([
            ('key_hash', '=', key_hash),
            ('is_active', '=', True),
        ], limit=1)

        if api_key:
            # Update last used time
            api_key.write({
                'last_used': fields.Datetime.now()
            })
            return True

        return False