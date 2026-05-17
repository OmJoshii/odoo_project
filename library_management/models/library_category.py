from odoo import models, fields

class LibraryCategory(models.Model):
    _name = 'library.category'
    _description = 'Book Category'

    name = fields.Char(string='Category Name', required=True)
    description = fields.Text(string='Description')

    # Many2many reverse side
    book_ids = fields.Many2many(
        comodel_name='library.book',
        relation='library_book_category_rel',
        column1='category_id',
        column2='book_id',
        string='Books'
    )