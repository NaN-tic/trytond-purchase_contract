# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import contract
from . import move
from . import purchase


def register():
    Pool.register(
        contract.PurchaseContract,
        contract.PurchaseContractLine,
        purchase.Purchase,
        purchase.PurchaseLine,
        move.Move,
        module='purchase_contract', type_='model')
