#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval
from trytond.modules.stock.move import STATES

__all__ = ['Move']
__metaclass__ = PoolMeta


class Move():
    __name__ = 'stock.move'

    origin_uom = fields.Many2One("product.uom", "Origin Uom", states=STATES,
        domain=[
            ('category', '=', Eval('product_uom_category')),
            ],
        depends=['state', 'product_uom_category'])
    origin_unit_digits = fields.Function(fields.Integer('Origin Unit Digits',
        on_change_with=['origin_uom']), 'on_change_with_origin_unit_digits')
    origin_quantity = fields.Float("Origin Quantity", states=STATES,
        digits=(16, Eval('origin_unit_digits', 2)),
        depends=['state', 'origin_unit_digits'])

    @classmethod
    def __setup__(cls):
        super(Move, cls).__setup__()
        if not cls.quantity.on_change:
            cls.quantity.on_change = []
        if not 'quantity' in cls.quantity.on_change:
            cls.quantity.on_change.append('quantity')

    def on_change_with_origin_unit_digits(self, name=None):
        if self.origin_uom:
            return self.origin_uom.digits
        return 2

    def on_change_product(self):
        res = super(Move, self).on_change_product()
        for field in ['uom', 'uom.rec_name', 'unit_digits']:
            if field in res:
                res["origin_%s" % field] = res[field]
        return res

    def on_change_uom(self):
        res = super(Move, self).on_change_uom()
        res['origin_uom'] = self.uom
        return res

    def on_change_quantity(self):
        return {
            'origin_quantity': self.quantity,
        }
