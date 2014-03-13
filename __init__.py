# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .contract import *
from .move import *


def register():
    Pool.register(
        PurchaseContract,
        PurchaseContractLine,
        Purchase,
        PurchaseLine,
        Move,
        module='purchase_contract', type_='model')
