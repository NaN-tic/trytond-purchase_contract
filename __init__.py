#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.

from trytond.pool import Pool

from .contract import *


def register():
    Pool.register(
        PurchaseContract,
        PurchaseContractLine,
        PurchaseLine,
        module='purchase_contract', type_='model')
