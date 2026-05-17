from odoo import models, fields, api

class LibraryAuthor(models.Model):
    _name = 'library.author'
    _description = 'Library Author'

    name = fields.Char(string='Name', required=True)
    bio = fields.Text(string='Biography')
    nationality = fields.Char(string='Nationality')
    birthdate = fields.Date(string='Date of Birth')
    email = fields.Char(string='Email')

    # One2many — one author has many books
    # This is the reverse side of the Many2one on library.book
    book_ids = fields.One2many(
        comodel_name='library.book',
        inverse_name='author_id',
        string='Books'
    )

    # Computed field — count of books
    book_count = fields.Integer(
        string='Number of Books',
        compute='_compute_book_count',
        store=True,
    )

    @api.depends('book_ids')
    def _compute_book_count(self):
        for rec in self:
            rec.book_count = len(rec.book_ids)