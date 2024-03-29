# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import And, Eval
from trytond.modules.stock.move import STATES

__all__ = ['Move']

ORIGIN_STATES = STATES.copy()
ORIGIN_STATES.update({
        'required': And(Eval('state', '') == 'done',
            Eval('origin_quantity_required', False)),
        'invisible': ~Eval('origin_quantity_required', False),
        })


class Move(metaclass=PoolMeta):
    __name__ = 'stock.move'

    origin_quantity_required = fields.Function(
        fields.Boolean('Origin Quantity Required'),
        'get_origin_quantity_required')
    origin_uom = fields.Many2One("product.uom", "Origin Uom", domain=[
            ('category', '=', Eval('product_uom_category')),
            ], states=ORIGIN_STATES,
        depends=['product_uom_category', 'state', 'origin_quantity_required'])
    origin_quantity = fields.Float("Origin Quantity",
        digits='origin_uom',
        states=ORIGIN_STATES,
        depends=['state', 'origin_quantity_required'])

    def get_origin_quantity_required(self, name):
        PurchaseLine = Pool().get('purchase.line')
        return (self.origin and isinstance(self.origin, PurchaseLine)
            and self.origin.contract_line and True or False)

    @fields.depends('origin_quantity_required', 'origin_quantity', 'product',
        'uom')
    def on_change_with_origin_uom(self):
        if not self.origin_quantity_required:
            return None
        if self.uom:
            return self.uom.id
        if self.product:
            return self.product.default_uom.id

    def on_change_product(self):
        super().on_change_product()
        self.origin_uom = self.uom

    @fields.depends('uom')
    def on_change_uom(self):
        self.origin_uom = self.uom

    @fields.depends('quantity')
    def on_change_quantity(self):
        self.origin_quantity = self.quantity
