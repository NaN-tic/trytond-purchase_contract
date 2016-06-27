# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, ModelSQL, Workflow, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Date, Eval, Or
from trytond.modules.product import price_digits

__all__ = ['Purchase', 'PurchaseLine',
    'PurchaseContract', 'PurchaseContractLine']
__metaclass__ = PoolMeta


class Purchase:
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
        cls.purchase_date.depends.append('has_contract_lines')
        cls._error_messages.update({
                'invalid_contract_dates': (
                    'The date of purchase "%(purchase)s" is not in the period '
                    'of contract "%(contract)s" selected in line "%(line)s".'),
                })

    @fields.depends('lines', 'lines.contract')
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
                self.raise_user_error('invalid_contract_dates', {
                        'purchase': self.rec_name,
                        'contract': contract.rec_name,
                        'line': line.rec_name,
                        })


class PurchaseLine():
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
        depends=['product', 'purchase'])

    @classmethod
    def __setup__(cls):
        super(PurchaseLine, cls).__setup__()
        cls.unit.on_change.add('contract_line')
        cls._error_messages.update({
                'invalid_invoice_method': ('The Purchase "%s" has some line '
                    'associated to a Purchase Contract but its Invoice Method '
                    'is not "Based On Shipment".'),
                })

    @classmethod
    def validate(cls, lines):
        super(PurchaseLine, cls).validate(lines)
        cls.check_invoice_method_with_contract(lines)

    @classmethod
    def check_invoice_method_with_contract(cls, lines):
        for line in lines:
            if (line.contract_line
                    and line.purchase.invoice_method != 'shipment'):
                cls.raise_user_error('invalid_invoice_method',
                    line.purchase.rec_name)

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
                self.contract_line = lines[0].id
                self.unit_price = Uom.compute_price(lines[0].unit,
                    lines[0].agreed_unit_price, self.unit)

    @fields.depends('contract_line', '_parent_contract_line.unit',
        '_parent_contract_line.agreed_unit_price')
    def on_change_quantity(self):
        pool = Pool()
        Uom = pool.get('product.uom')

        super(PurchaseLine, self).on_change_quantity()

        if self.contract_line:
            self.unit_price = Uom.compute_price(self.contract_line.unit,
                    self.contract_line.agreed_unit_price, self.unit)

    def get_invoice_line(self, invoice_type):
        pool = Pool()
        Uom = pool.get('product.uom')
        lines = super(PurchaseLine, self).get_invoice_line(invoice_type)
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
        cls._sql_constraints += [
            ('contract_product_uniq', 'unique (contract,product)',
                'There can not be two lines for the same product in a '
                'contract.')
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
