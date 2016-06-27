==========================
Purchase Contract Scenario
==========================

Imports::

    >>> import datetime
    >>> from dateutil.relativedelta import relativedelta
    >>> from decimal import Decimal
    >>> from operator import attrgetter
    >>> from proteus import config, Model, Wizard
    >>> from trytond.modules.company.tests.tools import create_company, \
    ...     get_company
    >>> from trytond.modules.account.tests.tools import create_fiscalyear, \
    ...     create_chart, get_accounts, create_tax
    >>> from.trytond.modules.account_invoice.tests.tools import \
    ...     set_fiscalyear_invoice_sequences, create_payment_term
    >>> today = datetime.date.today()

Create database::

    >>> config = config.set_trytond()
    >>> config.pool.test = True

Install purchase_contract::

    >>> Module = Model.get('ir.module')
    >>> purchase_module, = Module.find([('name', '=', 'purchase_contract')])
    >>> Module.install([purchase_module.id], config.context)
    >>> Wizard('ir.module.install_upgrade').execute('upgrade')

Create company::

    >>> _ = create_company()
    >>> company = get_company()

Reload the context::

    >>> User = Model.get('res.user')
    >>> Group = Model.get('res.group')
    >>> config._context = User.get_preferences(True, config.context)

Create fiscal year::

    >>> fiscalyear = set_fiscalyear_invoice_sequences(
    ...     create_fiscalyear(company))
    >>> fiscalyear.click('create_period')

Create chart of accounts::

    >>> _ = create_chart(company)
    >>> accounts = get_accounts(company)
    >>> receivable = accounts['receivable']
    >>> payable = accounts['payable']
    >>> revenue = accounts['revenue']
    >>> expense = accounts['expense']
    >>> cash = accounts['cash']

Create parties::

    >>> Party = Model.get('party.party')
    >>> supplier = Party(name='Supplier')
    >>> supplier.save()
    >>> customer = Party(name='Customer')
    >>> customer.save()

Create product::

    >>> ProductUom = Model.get('product.uom')
    >>> kg, = ProductUom.find([('name', '=', 'Kilogram')])
    >>> ProductTemplate = Model.get('product.template')
    >>> Product = Model.get('product.product')
    >>> product = Product()
    >>> template = ProductTemplate()
    >>> template.name = 'product'
    >>> template.default_uom = kg
    >>> template.type = 'goods'
    >>> template.purchasable = True
    >>> template.salable = True
    >>> template.list_price = Decimal('10')
    >>> template.cost_price = Decimal('5')
    >>> template.cost_price_method = 'fixed'
    >>> template.account_expense = expense
    >>> template.account_revenue = revenue
    >>> template.save()
    >>> product.template = template
    >>> product.save()

Create payment term::

    >>> payment_term = create_payment_term()
    >>> payment_term.save()

Create purchase contract::

    >>> Contract = Model.get('purchase.contract')
    >>> ContractLine = Model.get('purchase.contract.line')
    >>> contract = Contract()
    >>> contract.party = supplier
    >>> contract.party = supplier
    >>> contract.contract_type = 'destination'
    >>> contract.invoice_type = 'origin'
    >>> contract_line = contract.lines.new()
    >>> contract_line.product = product
    >>> contract.click('active')
    >>> contract.state
    u'active'

Purchase 5 products with an invoice method 'on shipment'::

    >>> Purchase = Model.get('purchase.purchase')
    >>> PurchaseLine = Model.get('purchase.line')
    >>> purchase = Purchase()
    >>> purchase.party = supplier
    >>> purchase.purchase_date = today
    >>> purchase.payment_term = payment_term
    >>> purchase.invoice_method = 'shipment'
    >>> purchase.has_contract_lines
    False
    >>> purchase_line = PurchaseLine()
    >>> purchase.lines.append(purchase_line)
    >>> purchase_line.type = 'comment'
    >>> purchase_line.description = 'Comment'
    >>> purchase.has_contract_lines
    False
    >>> purchase_line = PurchaseLine()
    >>> purchase.lines.append(purchase_line)
    >>> purchase_line.product = product
    >>> purchase_line.quantity = 2.0
    >>> purchase_line.contract = contract
    >>> purchase_line = PurchaseLine()
    >>> purchase.lines.append(purchase_line)
    >>> purchase_line.product = product
    >>> purchase_line.quantity = 3.0
    >>> purchase_line.contract = contract
    >>> purchase.has_contract_lines
    True
    >>> purchase.click('quote')
    >>> purchase.click('confirm')
    >>> purchase.click('process')
    >>> purchase.state
    u'processing'
    >>> purchase.reload()
    >>> len(purchase.moves), len(purchase.shipment_returns), len(purchase.invoices)
    (2, 0, 0)

Validate Shipments::

    >>> Move = Model.get('stock.move')
    >>> ShipmentIn = Model.get('stock.shipment.in')
    >>> shipment = ShipmentIn()
    >>> shipment.supplier = supplier
    >>> for move in purchase.moves:
    ...     incoming_move = Move(id=move.id)
    ...     incoming_move.origin_uom = incoming_move.uom
    ...     incoming_move.origin_quantity = 2.0
    ...     shipment.incoming_moves.append(incoming_move)
    >>> shipment.save()
    >>> shipment.origins == purchase.rec_name
    True
    >>> ShipmentIn.receive([shipment.id], config.context)
    >>> ShipmentIn.done([shipment.id], config.context)
    >>> purchase.reload()
    >>> len(purchase.shipments), len(purchase.shipment_returns)
    (1, 0)
    >>> contract.reload()
    >>> line, = contract.lines
    >>> line.consumed_quantity
    5.0

Open supplier invoice::

    >>> Invoice = Model.get('account.invoice')
    >>> invoice, = purchase.invoices
    >>> invoice.type
    u'in_invoice'
    >>> len(invoice.lines)
    2
    >>> for line in invoice.lines:
    ...     line.quantity == 2.0
    True
    True
    >>> contract.reload()
    >>> line, = contract.lines
    >>> line.consumed_quantity
    5.0
    >>> line.origin_quantity
    4.0
    >>> line.destination_quantity
    5.0

Purchase in diferent uom::

    >>> Purchase = Model.get('purchase.purchase')
    >>> PurchaseLine = Model.get('purchase.line')
    >>> g, = ProductUom.find([('name', '=', 'Gram')])
    >>> purchase = Purchase()
    >>> purchase.party = supplier
    >>> purchase.purchase_date = today
    >>> purchase.payment_term = payment_term
    >>> purchase.invoice_method = 'shipment'
    >>> purchase_line = PurchaseLine()
    >>> purchase.lines.append(purchase_line)
    >>> purchase_line.product = product
    >>> purchase_line.quantity = 200.0
    >>> purchase_line.contract = contract
    >>> purchase_line.unit = g
    >>> purchase.click('quote')
    >>> purchase.click('confirm')
    >>> purchase.click('process')


Validate Shipment::

    >>> shipment = ShipmentIn()
    >>> shipment.supplier = supplier
    >>> for move in purchase.moves:
    ...     incoming_move = Move(id=move.id)
    ...     incoming_move.origin_uom = incoming_move.uom
    ...     incoming_move.origin_quantity = 200.0
    ...     shipment.incoming_moves.append(incoming_move)
    >>> shipment.save()
    >>> shipment.origins == purchase.rec_name
    True
    >>> ShipmentIn.receive([shipment.id], config.context)
    >>> ShipmentIn.done([shipment.id], config.context)
    >>> purchase.reload()
    >>> len(purchase.shipments), len(purchase.shipment_returns)
    (1, 0)
    >>> contract.reload()
    >>> line, = contract.lines
    >>> line.consumed_quantity
    5.2
