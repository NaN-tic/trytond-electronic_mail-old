#This file is part electronic_mail module for Tryton.
#The COPYRIGHT file at the top level of this repository contains 
#the full copyright notices and license terms.
"Electronic Mail"
from __future__ import with_statement

import os
import base64
import re
from sys import getsizeof

try:
    import hashlib
except ImportError:
    hashlib = None
    import md5
from datetime import datetime
from time import mktime
from email.utils import parsedate

from trytond.model import ModelView, ModelSQL, fields
from trytond.config import CONFIG
from trytond.transaction import Transaction
from trytond.pool import Pool

__all__ = ['Mailbox', 'MailboxParent', 'ReadUser', 'WriteUser',
    'ElectronicMail', 'Header']

class Mailbox(ModelSQL, ModelView):
    "Mailbox"
    __name__ = "electronic.mail.mailbox"

    name = fields.Char('Name', required=True)
    user = fields.Many2One('res.user', 'Owner')
    parents = fields.Many2Many(
             'electronic.mail.mailbox.mailbox',
             'parent', 'child' ,'Parents')
    subscribed = fields.Boolean('Subscribed')
    read_users = fields.Many2Many('electronic.mail.mailbox.read.res.user',
            'mailbox', 'user', 'Read Users')
    write_users = fields.Many2Many('electronic.mail.mailbox.write.res.user',
            'mailbox', 'user', 'Write Users')


class MailboxParent(ModelSQL):
    'Mailbox - parent - Mailbox'
    __name__ = 'electronic.mail.mailbox.mailbox'

    parent = fields.Many2One('electronic.mail.mailbox', 'Parent',
            ondelete='CASCADE', required=True, select=1)
    child = fields.Many2One('electronic.mail.mailbox', 'Child',
            ondelete='CASCADE', required=True, select=1)


class ReadUser(ModelSQL):
    'Electronic Mail - read - User'
    __name__ = 'electronic.mail.mailbox.read.res.user'

    mailbox = fields.Many2One('electronic.mail.mailbox', 'Mailbox',
            ondelete='CASCADE', required=True, select=1)
    user = fields.Many2One('res.user', 'User', ondelete='CASCADE',
            required=True, select=1)


class WriteUser(ModelSQL):
    'Mailbox - write - User'
    __name__ = 'electronic.mail.mailbox.write.res.user'

    mailbox = fields.Many2One('electronic.mail.mailbox', 'mailbox',
            ondelete='CASCADE', required=True, select=1)
    user = fields.Many2One('res.user', 'User', ondelete='CASCADE',
            required=True, select=1)


class ElectronicMail(ModelSQL, ModelView):
    "E-mail"
    __name__ = 'electronic.mail'
    _order_name = 'date'

    mailbox = fields.Many2One(
        'electronic.mail.mailbox', 'Mailbox', required=True)
    from_ = fields.Char('From')
    sender = fields.Char('Sender')
    to = fields.Char('To')
    cc = fields.Char('CC')
    bcc = fields.Char('BCC')
    subject = fields.Char('Subject')
    date = fields.DateTime('Date')
    message_id = fields.Char('Message-ID', help='Unique Message Identifier')
    in_reply_to = fields.Char('In-Reply-To')
    headers = fields.One2Many(
        'electronic.mail.header', 'electronic_mail', 'Headers')
    digest = fields.Char('MD5 Digest', size=32)
    collision = fields.Integer('Collision')
    email = fields.Function(fields.Binary('Email'), 'get_email', setter='set_email')
    flag_send = fields.Boolean('Sent', readonly=True)
    flag_seen = fields.Boolean('Seen')
    flag_answered = fields.Boolean('Answered')
    flag_flagged = fields.Boolean('Flagged')
    flag_draft = fields.Boolean('Draft')
    flag_recent = fields.Boolean('Recent')
    template = fields.Boolean('Template')
    size = fields.Integer('Size')
    mailbox_owner = fields.Function(
        fields.Many2One('res.user', 'Owner'),
        'get_mailbox_owner', searcher='search_mailbox_owner')
    mailbox_read_users = fields.Function(
        fields.One2Many('res.user', None, 'Read Users'),
        'get_mailbox_users', searcher='search_mailbox_users')
    mailbox_write_users = fields.Function(
        fields.One2Many('res.user', None, 'Write Users'),
        'get_mailbox_users', searcher='search_mailbox_users')

    @classmethod
    def __setup__(cls):
        super(ElectronicMail, cls).__setup__()
        cls._order.insert(0, ('date', 'DESC'))

    @staticmethod
    def default_collision():
        return 0

    @staticmethod
    def default_flag_seen():
        return False

    @staticmethod
    def default_flag_answered():
        return False

    @staticmethod
    def default_flag_flagged():
        return False

    @staticmethod
    def default_flag_recent():
        return False

    @staticmethod
    def default_template():
        return False

    @classmethod
    def get_rec_name(cls, records, name):
        if not records:
            return {}
        res = {}
        for mail in records:
            res[mail.id] = '%s (ID: %s)' % (mail.subject, mail.id)
        return res

    @classmethod
    def get_mailbox_owner(cls, records, name):
        "Returns owner of mailbox"
        mails = records
        return dict([(mail.id, mail.mailbox.user.id) for mail in mails])

    @classmethod
    def get_mailbox_users(cls, records, name):
        assert name in ('mailbox_read_users', 'mailbox_write_users')
        res = {}
        for mail in records:
            if name == 'mailbox_read_users':
                res[mail.id] = [x.id for x in mail.mailbox['read_users']]
            else:
                res[mail.id] = [x.id for x in mail.mailbox['write_users']]
        return res

    @classmethod
    def search_mailbox_owner(self, name, clause):
        return [('mailbox.user',) + clause[1:]]

    @classmethod
    def search_mailbox_users(self, name, clause):
        return [('mailbox.' + name[8:],) + clause[1:]]

    @staticmethod
    def _get_email(electronic_mail):
        """
        Returns the email object from reading the FS
        :param electronic_mail: Browse Record of the mail
        """
        db_name = Transaction().cursor.dbname
        value = u''
        if electronic_mail.digest:
            filename = electronic_mail.digest
            if electronic_mail.collision:
                filename = filename + '-' + str(electronic_mail.collision)
            filename = os.path.join(
                CONFIG['data_path'], db_name, 
                'email', filename[0:2], filename)
            try:
                with open(filename, 'rb') as file_p:
                    value = buffer(file_p.read())
            except IOError:
                pass
        return value

    def get_email(self, name):
        """Fetches email from the data_path as email object
        """
        return self._get_email(self) or False

    @classmethod
    def set_email(cls, records, name, data):
        """Saves an email to the data path

        :param data: Email as string
        """
        if data is False or data is None:
            return
        db_name = Transaction().cursor.dbname
        # Prepare Directory <DATA PATH>/<DB NAME>/email
        directory = os.path.join(CONFIG['data_path'], db_name)
        if not os.path.isdir(directory):
            os.makedirs(directory, 0770)
        digest = cls.make_digest(data)
        directory = os.path.join(directory, 'email', digest[0:2])
        if not os.path.isdir(directory):
            os.makedirs(directory, 0770)
        # Filename <DIRECTORY>/<DIGEST>
        filename = os.path.join(directory, digest)
        collision = 0

        if not os.path.isfile(filename):
            # File doesnt exist already
            with open(filename, 'w') as file_p:
                file_p.write(data)
        else:
            # File already exists, may be its the same email data
            # or maybe different. 

            # Case 1: If different: we have to write file with updated
            # Collission index

            # Case 2: Same file: Leave it as such
            with open(filename, 'r') as file_p:
                data2 = file_p.read()
            if data != data2:
                cursor = Transaction().cursor
                cursor.execute(
                    'SELECT DISTINCT(collision) FROM electronic_mail '
                    'WHERE digest = %s AND collision !=0 '
                    'ORDER BY collision', (digest,))
                collision2 = 0
                for row in cursor.fetchall():
                    collision2 = row[0]
                    filename = os.path.join(
                        directory, digest + '-' + str(collision2))
                    if os.path.isfile(filename):
                        with open(filename, 'r') as file_p:
                            data2 = file_p.read()
                        if data == data2:
                            collision = collision2
                            break
                if collision == 0:
                    collision = collision2 + 1
                    filename = os.path.join(
                        directory, digest + '-' + str(collision))
                    with open(filename, 'w') as file_p:
                        file_p.write(data)
        cls.write(records, {'digest': digest, 'collision': collision})

    @staticmethod
    def make_digest(data):
        """
        Returns a digest from the mail

        :param data: Data String
        :return: Digest
        """
        if hashlib:
            digest = hashlib.md5(data).hexdigest()
        else:
            digest = md5.new(data).hexdigest()
        return digest

    @classmethod
    def create_from_email(self, mail, mailbox):
        """
        Creates a mail record from a given mail
        :param mail: email object
        :param mailbox: ID of the mailbox
        """
        Header = Pool().get('electronic.mail.header')
        email_date = mail.get('date') and datetime.fromtimestamp(
                mktime(parsedate(mail.get('date'))))
        values = {
            'mailbox': mailbox,
            'from_': mail.get('from'),
            'sender': mail.get('sender'),
            'to': mail.get('to'),
            'cc': mail.get('cc'),
            'bcc': mail.get('bcc'),
            'subject': mail.get('subject'),
            'date': email_date,
            'message_id': mail.get('message-id'),
            'in_reply_to': mail.get('in-reply-to'),
            'email': mail.as_string(),
            'size': getsizeof(mail.as_string()),
            }
        email = self.create([values])[0]
        Header.create_from_email(mail, email)
        return email

    @staticmethod
    def get_email_valid(email):
        """Get if email is valid. @ and . characters validation
        :email: str
        return: True or False
        """
        def get_validate_email(email):
            #  ! # $ % & ' * + - / = ? ^ _ ` { | } ~ 
            if not re.match(r"^[A-Za-z0-9\.!#\$%&'\*\+-/=\?\^_`\{|\}~]+@[A-Za-z0-9\.!#\$%&'\*\+-/=\?\^_`\{|\}~]+\.[a-zA-Z]*$", email):
                return False
            return True

        if not email:
            return False

        email = email.replace(';',',') #replace separator emails ; -> ,
        emails = email.split(',')
        if len(emails)>0:
            for email in emails:
                if not get_validate_email(email):
                    return False
                    break
        return True


class Header(ModelSQL, ModelView):
    "Header fields"
    __name__ = 'electronic.mail.header'

    name = fields.Char('Name', help='Name of Header Field')
    value = fields.Char('Value', help='Value of Header Field')
    electronic_mail = fields.Many2One('electronic.mail', 'e-mail')

    @classmethod
    def create_from_email(self, mail, mail_id):
        """
        :param mail: Email object
        :param mail_id: ID of the email from electronic_mail
        """
        to_create = []
        for name, value in mail.items():
            values = {
                'electronic_mail':mail_id,
                'name':name,
                'value':value,
                }
            to_create.append(values)

        if to_create:
            self.create(to_create)
        return True
