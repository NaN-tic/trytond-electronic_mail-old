# -*- coding: UTF-8 -*-
#This file is part electronic_mail module for Tryton.
#The COPYRIGHT file at the top level of this repository contains 
#the full copyright notices and license terms.
from trytond.pool import Pool
from electronic_mail import *

def register():
    Pool.register(
        Mailbox,
        MailboxParent,
        ReadUser,
        WriteUser,
        ElectronicMail,
        module='electronic_mail', type_='model')
