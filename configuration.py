# This file is part of the electronic_mail_configuration module for Tryton.
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelView, ModelSingleton, ModelSQL, fields

__all__ = ['ElectronicMailConfiguration']


class ElectronicMailConfiguration(ModelSingleton, ModelSQL, ModelView):
    'Electronic Mail Configuration'
    __name__ = 'electronic.mail.configuration'
    sent = fields.Property(fields.Many2One('electronic.mail.mailbox',
        'Sent', required=True))
    draft = fields.Property(fields.Many2One('electronic.mail.mailbox',
        'Draft', required=True))
    error = fields.Property(fields.Many2One('electronic.mail.mailbox',
        'Error', required=True))
    outbox = fields.Property(fields.Many2One('electronic.mail.mailbox',
        'Outbox', required=True))
