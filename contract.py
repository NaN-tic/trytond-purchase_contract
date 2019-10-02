# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, ModelSQL, Workflow, fields, Unique
from trytond.pool import Pool
from trytond.pyson import Eval
from trytond.modules.product import price_digits

__all__ = ['PurchaseContract', 'PurchaseContractLine']


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
                    'icon': 'tryton-forward',
                    },
                'cancel': {
                    'invisible': Eval('state') != 'active',
                    'icon': 'tryton-cancel',
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
    unit = fields.Function(fields.Many2One('product.uom', 'Unit'),
        'on_change_with_unit')
    unit_digits = fields.Function(fields.Integer('Unit Digits'),
        'on_change_with_unit_digits')
    agreed_quantity = fields.Float('Agreed Quantity',
        digits=(16, Eval('unit_digits', 2)), depends=['unit_digits'])
    agreed_unit_price = fields.Numeric('Agreed Unit Price',
        digits=price_digits, required=True)
    lines = fields.One2Many('purchase.line', 'contract_line',
        'Lines', readonly=True)
    moves = fields.Function(fields.One2Many('stock.move', None, 'Moves',
            readonly=True),
        'get_moves')
    origin_quantity = fields.Function(fields.Float('Origin Quantity',
            digits=(16, Eval('unit_digits', 2)), depends=['unit_digits']),
        'get_quantities')
    destination_quantity = fields.Function(fields.Float('Destination Quantity',
            digits=(16, Eval('unit_digits', 2)), depends=['unit_digits']),
        'get_quantities')
    consumed_quantity = fields.Function(fields.Float('Consumed Quantity',
            digits=(16, Eval('unit_digits', 2)), depends=['unit_digits']),
        'get_quantities')

    @classmethod
    def __setup__(cls):
        super(PurchaseContractLine, cls).__setup__()
        t = cls.__table__()
        cls._sql_constraints += [
            ('contract_product_uniq', Unique(t, t.contract, t.product),
                'purchase_contract.msg_contract_product_uniq'),
            ]

    def get_rec_name(self, name):
        return '%s, %s, %s %s, %s' % (self.contract.rec_name,
            self.product.rec_name, self.agreed_quantity, self.unit.symbol,
            self.agreed_unit_price)

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        default = default.copy()
        default['lines'] = None

        return super(PurchaseContractLine, cls).copy(lines, default=default)

    @fields.depends('product')
    def on_change_with_unit(self, name=None):
        if self.product:
            return self.product.purchase_uom.id
        return None

    @fields.depends('unit')
    def on_change_with_unit_digits(self, name=None):
        if self.unit:
            return self.unit.digits
        return 2

    @fields.depends('product')
    def on_change_with_agreed_unit_price(self):
        return self.product.cost_price if self.product else None

    def get_moves(self, name):
        moves = []
        for line in self.lines:
            if line.purchase.state in ['processing', 'done']:
                moves.extend([m.id for m in line.moves
                        if m.state not in ('draft' 'cancel')])
        return moves

    @classmethod
    def get_quantities(cls, lines, names):
        pool = Pool()
        Uom = pool.get('product.uom')

        res = {}
        line_ids = [l.id for l in lines]
        for name in names:
            res[name] = {}.fromkeys(line_ids, 0.0)

        for line in lines:
            origin = destination = 0.0
            for move in line.moves:
                origin += Uom.compute_qty(move.origin_uom,
                    move.origin_quantity, to_uom=move.product.default_uom)
                destination += move.internal_quantity
            if 'origin_quantity' in names:
                res['origin_quantity'][line.id] = origin
            if 'destination_quantity' in names:
                res['destination_quantity'][line.id] = destination
            if 'consumed_quantity' in names:
                if line.contract.contract_type == 'origin':
                    res['consumed_quantity'][line.id] = origin
                else:
                    res['consumed_quantity'][line.id] = destination
        return res
