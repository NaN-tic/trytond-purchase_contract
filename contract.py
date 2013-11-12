#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.model import ModelView, ModelSQL, Workflow, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Bool, Not

__all__ = ['PurchaseLine', 'PurchaseContract', 'PurchaseContractLine']
__metaclass__ = PoolMeta


class PurchaseLine():
    'Purchase Line'
    __name__ = 'purchase.line'

    contract = fields.Function(fields.Many2One('purchase.contract', 'Contract',
            states={
                'readonly': Not(Bool(Eval('product')))
                },
            domain=[
                ('state', '=', 'active'),
                ('lines.product', '=', Eval('product')),
                ('party', '=', Eval('_parent_purchase', {}).get('party')),
            ], depends=['product']), 'get_contract',
        setter='set_contract')
    contract_line = fields.Many2One('purchase.contract.line', 'Contract Line')

    def get_contract(self, name=None):
        if self.contract_line and self.contract_line.contract:
            return self.contract_line.contract.id

    @classmethod
    def set_contract(cls, lines, name, value):
        if not value:
            return
        ContractLines = Pool().get('purchase.contract.line')
        for purchase_line in lines:
            if purchase_line.product:
                lines = ContractLines.search([
                            ('contract', '=', value),
                            ('product', '=', purchase_line.product),
                        ])
                if len(lines) > 0:
                    line = lines[0]
                    cls.write([purchase_line], {
                        'contract_line': line,
                        })

    def on_change_product(self):
        ContractLines = Pool().get('purchase.contract.line')
        res = super(PurchaseLine, self).on_change_product()
        if self.purchase and self.purchase.party and self.product is not None:
            lines = ContractLines.search([
                ('contract.party', '=', self.purchase.party),
                ('product', '=', self.product),
                ('contract.state', '=', 'active'),
                ], limit=1)
            if lines:
                res['contract'] = lines[0].contract.id
        return res

    def get_invoice_line(self, invoice_type):
        pool = Pool()
        Uom = pool.get('product.uom')
        lines = super(PurchaseLine, self).get_invoice_line(invoice_type)
        if len(lines) != 1:
            return lines
        line, = lines
        contract = self.contract
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

_STATES = {
    'readonly': Eval('state') != 'draft',
}

_DEPENDS = ['state']


class PurchaseContract(Workflow, ModelSQL, ModelView):
    'Purchase Contract'
    __name__ = 'purchase.contract'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('cancel', 'Canceled'),
    ], 'State', readonly=True, required=True)
    party = fields.Many2One('party.party', 'Supplier', required=True,
        states=_STATES, depends=_DEPENDS)
    contract_type = fields.Selection([
            ('origin', 'Origin'),
            ('destination', 'Destination'),
            ], 'Contract quantity', required=True, states=_STATES,
        depends=_DEPENDS, help='Quantity used to calculate consumed quantity')
    invoice_type = fields.Selection([
            ('origin', 'Origin'),
            ('destination', 'Destination'),
            ], 'Quantity to invoice', required=True, states=_STATES,
        depends=_DEPENDS, help='Quantity used to create invoices')
    start_date = fields.Date('Start Date', states=_STATES, depends=_DEPENDS)
    end_date = fields.Date('End Date', states=_STATES, depends=_DEPENDS)
    lines = fields.One2Many('purchase.contract.line', 'contract', 'Lines',
        states=_STATES, depends=_DEPENDS)

    @classmethod
    def __setup__(cls):
        super(PurchaseContract, cls).__setup__()
        cls._transitions |= set((
                ('draft', 'active'),
                ('active', 'cancel'),
                ))
        cls._buttons.update({
                'active': {
                    'invisible': Eval('state') != 'draft',
                    },
                'cancel': {
                    'invisible': Eval('state') != 'active',
                    },
                 })

    @classmethod
    def copy(cls, contracts, default=None):
        pool = Pool()
        Line = pool.get('purchase.contract.line')

        if default is None:
            default = {}
        default = default.copy()
        default['state'] = 'draft'
        default['lines'] = None
        default['start_date'] = None
        default['end_date'] = None

        new_contracts = []
        for contract in contracts:
            new_contract, = super(PurchaseContract, cls).copy(
                [contract], default=default)
            Line.copy(contract.lines, default={
                    'contract': new_contract.id,
                    })
            new_contracts.append(new_contract)
        return new_contracts

    @staticmethod
    def default_state():
        return 'draft'

    @staticmethod
    def default_contract_type():
        return 'destination'

    @staticmethod
    def default_invoice_type():
        return 'destination'

    def get_rec_name(self, name):
        ret = self.party.rec_name
        if self.start_date:
            ret += ' - %s' % (self.start_date)
        return ret

    @classmethod
    @ModelView.button
    @Workflow.transition('active')
    def active(cls, contracts):
        Date = Pool().get('ir.date')
        actives = [c for c in contracts if not c.start_date]
        cls.write(actives, {'start_date': Date.today()})

    @classmethod
    @ModelView.button
    @Workflow.transition('cancel')
    def cancel(cls, contracts):
        Date = Pool().get('ir.date')
        cancels = [c for c in contracts if not c.end_date]
        cls.write(cancels, {'end_date': Date.today()})


class PurchaseContractLine(ModelSQL, ModelView):
    'Purchase Contract Line'
    __name__ = 'purchase.contract.line'

    contract = fields.Many2One('purchase.contract', 'Contract', required=True,
        ondelete='CASCADE')
    product = fields.Many2One('product.product', 'Product', required=True,
        domain=[('purchasable', '=', True)])
    unit = fields.Function(fields.Many2One('product.uom', 'Unit',
        on_change_with=['product']), 'on_change_with_unit')
    unit_digits = fields.Function(fields.Integer('Unit Digits',
            on_change_with=['unit']), 'on_change_with_unit_digits')
    agreed_quantity = fields.Float('Agreed Quantity',
        digits=(16, Eval('unit_digits', 2)),
        depends=['unit_digits'])
    origin_quantity = fields.Function(fields.Float('Origin Quantity',
        digits=(16, Eval('unit_digits', 2)),
        depends=['unit_digits']), 'get_origin_quantity')
    destination_quantity = fields.Function(fields.Float('Destination Quantity',
        digits=(16, Eval('unit_digits', 2)),
        depends=['unit_digits']), 'get_destination_quantity')
    lines = fields.One2Many('purchase.line', 'contract_line',
        'Lines', readonly=True)
    moves = fields.Function(fields.One2Many('stock.move', None, 'Moves',
            readonly=True), 'get_moves')
    consumed_quantity = fields.Function(fields.Float('Consumed Quantity',
        digits=(16, Eval('unit_digits', 2)),
        depends=['unit_digits']), 'get_consumed_quantity')

    @classmethod
    def __setup__(cls):
        super(PurchaseContractLine, cls).__setup__()
        cls._sql_constraints += [
            ('contract_product_uniq', 'unique (contract,product)',
                'unique_product')
            ]

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['lines'] = None

        return super(PurchaseContractLine, cls).copy(lines, default=default)

    def on_change_with_unit(self, name=None):
        if self.product:
            return self.product.purchase_uom.id
        return None

    def on_change_with_unit_digits(self, name=None):
        if self.unit:
            return self.unit.digits
        return 2

    def get_moves(self, name):
        moves = []
        for line in self.lines:
            if line.purchase.state in ['confirmed', 'done']:
                moves.extend([x.id for x in line.moves])
        return moves

    def get_destination_quantity(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        if not self.lines:
            return 0.0
        values = [(l.quantity, l.unit, l.product.template.default_uom)
                for l in self.lines if l.purchase.state in
                ['confirmed', 'done']
            ]
        quantity = 0.0
        for qty, from_uom, to_uom in values:
            quantity += Uom.compute_qty(from_uom, qty, to_uom=to_uom)
        return quantity

    def get_origin_quantity(self, name=None):
        pool = Pool()
        Uom = pool.get('product.uom')
        if not self.moves:
            return 0.0

        values = [(l.origin_quantity or l.quantity, l.origin_uom or l.uom,
                l.product.default_uom) for l in self.moves
                  ]
        quantity = 0.0
        for qty, from_uom, to_uom in values:
            quantity += Uom.compute_qty(from_uom, qty, to_uom=to_uom)
        return quantity

    def get_consumed_quantity(self, name):
        return getattr(self, "%s_quantity" % self.contract.contract_type)
