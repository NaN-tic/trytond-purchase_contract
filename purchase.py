# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Date, Eval, Or
from trytond.exceptions import UserError
from trytond.i18n import gettext

__all__ = ['Purchase', 'PurchaseLine']


class Purchase(metaclass=PoolMeta):
    __name__ = 'purchase.purchase'
    has_contract_lines = fields.Function(fields.Boolean('Has Contract Lines?'),
        'on_change_with_has_contract_lines')

    @classmethod
    def __setup__(cls):
        super(Purchase, cls).__setup__()
        if cls.purchase_date.states.get('required'):
            cls.purchase_date.states['required'] = Or(
                cls.purchase_date.states['required'],
                Eval('has_contract_lines', False))
        else:
            cls.purchase_date.states['required'] = Eval('has_contract_lines',
                False)
        cls.purchase_date.depends.add('has_contract_lines')

    @fields.depends('lines')
    def on_change_with_has_contract_lines(self, name=None):
        if not self.lines:
            return False
        return any(getattr(l, 'contract_line') for l in self.lines)

    @classmethod
    def validate(cls, purchases):
        super(Purchase, cls).validate(purchases)
        for purchase in purchases:
            purchase.check_contract_line_dates()

    def check_contract_line_dates(self):
        for line in self.lines:
            if not line.contract_line:
                continue
            contract = line.contract_line.contract
            if (contract.start_date
                    and self.purchase_date < contract.start_date
                    or contract.end_date
                    and self.purchase_date > contract.end_date):
                raise UserError(gettext('purchase_contract.'
                        'msg_invalid_contract_dates',
                        purchase=self.rec_name,
                        contract=contract.rec_name,
                        line=line.rec_name,
                        ))


class PurchaseLine(metaclass=PoolMeta):
    __name__ = 'purchase.line'

    contract_line = fields.Many2One('purchase.contract.line', 'Contract Line',
        domain=[
            ('contract.state', '=', 'active'),
            ('product', '=', Eval('product')),
            ('contract.party', '=', Eval('_parent_purchase', {}).get('party')),
            ['OR',
                ('contract.start_date', '=', None),
                ('contract.start_date', '<=',
                    Eval('_parent_purchase', {}).get('purchase_date', Date())),
                ],
            ['OR',
                ('contract.end_date', '=', None),
                ('contract.end_date', '>=',
                    Eval('_parent_purchase', {}).get('purchase_date', Date())),
                ],
            ],
        states={
            'invisible': Eval('type') != 'line',
            },
        depends=['product', 'purchase', 'type'])

    @classmethod
    def __setup__(cls):
        super(PurchaseLine, cls).__setup__()
        cls.unit.on_change.add('contract_line')

    @classmethod
    def validate(cls, lines):
        super(PurchaseLine, cls).validate(lines)
        cls.check_invoice_method_with_contract(lines)

    @classmethod
    def check_invoice_method_with_contract(cls, lines):
        for line in lines:
            if (line.contract_line
                    and line.purchase.invoice_method != 'shipment'):
                raise UserError(gettext('purchase_contract.'
                        'msg_invalid_invoice_method',
                        purchase=line.purchase.rec_name))

    def on_change_product(self):
        pool = Pool()
        ContractLines = pool.get('purchase.contract.line')
        Date = pool.get('ir.date')
        Uom = pool.get('product.uom')

        super(PurchaseLine, self).on_change_product()
        if self.purchase and self.purchase.party and self.product is not None:
            lines = ContractLines.search([
                    ('contract.party', '=', self.purchase.party),
                    ('product', '=', self.product),
                    ('contract.state', '=', 'active'),
                    ['OR',
                        ('contract.start_date', '=', None),
                        ('contract.start_date', '<=',
                            self.purchase.purchase_date or Date.today()),
                        ],
                    ['OR',
                        ('contract.end_date', '=', None),
                        ('contract.end_date', '>=',
                            self.purchase.purchase_date or Date.today()),
                        ],
                    ], limit=1)
            if lines:
                self.contract_line = lines[0]
                self.unit_price = Uom.compute_price(lines[0].unit,
                    lines[0].agreed_unit_price, self.unit)

    @fields.depends('_parent_contract_line.id', 'contract_line')
    def on_change_quantity(self):
        pool = Pool()
        Uom = pool.get('product.uom')

        super(PurchaseLine, self).on_change_quantity()
        if self.contract_line:
            self.unit_price = Uom.compute_price(self.contract_line.unit,
                    self.contract_line.agreed_unit_price, self.unit)

    def get_invoice_line(self):
        pool = Pool()
        Uom = pool.get('product.uom')
        lines = super(PurchaseLine, self).get_invoice_line()
        if len(lines) != 1:
            return lines

        line, = lines
        contract = self.contract_line and self.contract_line.contract
        if (contract and contract.invoice_type == 'origin' and
                self.purchase.invoice_method == 'shipment' and self.product
                and self.product.type != 'service'):
            quantity = 0.0
            for move in self.moves:
                if move.state == 'done':
                    quantity += Uom.compute_qty(move.origin_uom,
                        move.origin_quantity, self.unit)
            skip_ids = set(l.id for i in self.purchase.invoices_recreated
                for l in i.lines)
            for old_invoice_line in self.invoice_lines:
                if old_invoice_line.type != 'line':
                    continue
                if old_invoice_line.id not in skip_ids:
                    quantity -= Uom.compute_qty(old_invoice_line.unit,
                            old_invoice_line.quantity, self.unit)
            line.quantity = quantity

        return [line]
