# This file is part electronic_mail module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from trytond.pool import PoolMeta
from trytond.model import fields

__all__ = ['User']
__metaclass__ = PoolMeta


class User:
    __name__ = "res.user"
    signature_html = fields.Text('Signature')

    @classmethod
    def __setup__(cls):
        super(User, cls).__setup__()
        cls._preferences_fields.extend(['signature_html'])
