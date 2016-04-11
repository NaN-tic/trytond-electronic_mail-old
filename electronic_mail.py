# This file is part of electronic_mail module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from __future__ import with_statement
from itertools import groupby
from _socket import gaierror, error
from datetime import datetime
from sys import getsizeof
from time import mktime
from trytond.config import config
from trytond.exceptions import UserError
from trytond.model import ModelView, ModelSQL, fields
from trytond.pool import Pool
from trytond.pyson import Bool, Eval, PYSONEncoder
from trytond.tools.misc import reduce_ids
from trytond.transaction import Transaction
from email import message_from_string
from email.utils import parsedate, parseaddr, getaddresses
from email.header import decode_header, make_header
import operator
import logging
import os
from smtplib import SMTPAuthenticationError, SMTPException
import chardet
import mimetypes

logger = logging.getLogger(__name__)

try:
    import hashlib
except ImportError:
    hashlib = None
    import md5
    
try:
    from emailvalid import check_email
    CHECK_EMAIL = True
except ImportError:
    CHECK_EMAIL = False
    logger.warning('Unable to import emailvalid. Email validation disabled.')


def _make_header(data, charset='utf-8'):
    return str(make_header([(data, charset)]))

def _decode_header(data):
    if data is None:
        return
    decoded_headers = decode_header(data)
    headers = []
    for decoded_str, charset in decoded_headers:
        if charset:
            headers.append(unicode(decoded_str, charset))
        else:
            headers.append(unicode(decoded_str, 'utf8'))
    return " ".join(headers)

def _decode_body(part):
    charset = str(part.get_content_charset())
    payload = part.get_payload(decode=True)
    if not charset or charset == 'None':
        charset = chardet.detect(payload).get('encoding')
    return payload.decode(charset).strip()

def msg_from_string(email_file):
    " Convert email file to string"
    if isinstance(email_file, (bytearray)):
        return message_from_string(email_file)
    return None


__all__ = ['Mailbox', 'ReadUser', 'WriteUser', 'ElectronicMail']


class Mailbox(ModelSQL, ModelView):
    "Mailbox"
    __name__ = "electronic.mail.mailbox"

    name = fields.Char('Name', required=True)
    user = fields.Many2One('res.user', 'Owner')
    read_users = fields.Many2Many('electronic.mail.mailbox.read.res.user',
            'mailbox', 'user', 'Read Users')
    write_users = fields.Many2Many('electronic.mail.mailbox.write.res.user',
            'mailbox', 'user', 'Write Users')
    scheduler = fields.Boolean('Scheduler',
        help='Send emails in this mailbox by the scheduler')
    smtp_server = fields.Many2One('smtp.server', 'SMTP Server',
        domain=[('state', '=', 'done')], states={
            'required': Eval('scheduler', True),
        }, depends=['scheduler'])

    @classmethod
    def __setup__(cls):
        super(Mailbox, cls).__setup__()
        cls._error_messages.update({
                'foreign_model_exist': 'You can not delete this mailbox '
                    'because it has electronic mails.',
                'menu_exist': 'This mailbox has already a menu.\nPlease, '
                    'refresh the menu to see it.',
                })
        cls._buttons.update({
                'create_menu': {
                    'invisible': Bool(Eval('menu')),
                    },
                })

    @staticmethod
    def default_scheduler():
        return False

    @classmethod
    def check_xml_record(cls, records, values):
        return True

    @classmethod
    def delete(cls, mailboxes):
        # TODO Add a wizard that pops up a window telling that menu is deleted
        # and that in order to see it, you must type ALT+T or refresh the menu
        # by clicking menu User > Refresh Menu
        pool = Pool()
        Menu = pool.get('ir.ui.menu')
        Action = pool.get('ir.action')
        ActWindow = pool.get('ir.action.act_window')
        ActionKeyword = pool.get('ir.action.keyword')
        ActWindowView = pool.get('ir.action.act_window.view')

        encoder = PYSONEncoder()

        act_windows = []
        actions = []
        keywords = []
        menus = []
        act_window_views = []
        for mailbox in mailboxes:
            act_windows.extend(ActWindow.search([
                    ('res_model', '=', 'electronic.mail'),
                    ('domain', '=', encoder.encode([('mailbox', '=', mailbox.id)])),
                    ]))
            actions.extend([a_w.action for a_w in act_windows])
            keywords.extend(ActionKeyword.search([('action', 'in', actions)]))
            menus.extend([k.model for k in keywords])
            act_window_views.extend(ActWindowView.search([
                    ('act_window', 'in', [a_w.id for a_w in act_windows]),
                    ]))

        ActWindowView.delete(act_window_views)
        ActWindow.delete(act_windows)
        ActionKeyword.delete(keywords)
        Action.delete(actions)
        Menu.delete(menus)
        return super(Mailbox, cls).delete(mailboxes)

    @classmethod
    def write(cls, *args):
        # TODO Add a wizard that pops up a window telling that menu is updated
        # and that in order to see it, you must type ALT+T or refresh the menu
        # by clicking menu User > Refresh Menu
        pool = Pool()
        ActWindow = pool.get('ir.action.act_window')
        Action = pool.get('ir.action')
        ActionKeyword = pool.get('ir.action.keyword')
        Menu = pool.get('ir.ui.menu')

        encoder = PYSONEncoder()

        acts = iter(args)
        for mailboxes, values in zip(acts, acts):
            if 'name' in values:
                actions = []
                menus = []
                for mailbox in mailboxes:
                    act_windows = ActWindow.search([
                            ('res_model', '=', 'electronic.mail'),
                            ('domain', '=', encoder.encode([('mailbox', '=', mailbox.id)])),
                            ])
                    actions.extend([a_w.action for a_w in act_windows])
                    keywords = ActionKeyword.search([
                            ('action', 'in', actions)])
                    menus.extend([k.model for k in keywords])
                Action.write(actions, {'name': values['name']})
                Menu.write(menus, {'name': values['name']})
        super(Mailbox, cls).write(*args)

    @classmethod
    @ModelView.button
    def create_menu(cls, mailboxes):
        # TODO Add a wizard that pops up a window telling that menu is created
        # and that in order to see it, you must type ALT+T or refresh the menu
        # by clicking menu User > Refresh Menu
        pool = Pool()
        ModelData = pool.get('ir.model.data')
        Menu = pool.get('ir.ui.menu')
        Action = pool.get('ir.action')
        ActWindow = pool.get('ir.action.act_window')
        ActionKeyword = pool.get('ir.action.keyword')
        ActWindowView = pool.get('ir.action.act_window.view')
        View = pool.get('ir.ui.view')

        encoder = PYSONEncoder()

        for mailbox in mailboxes:
            act_windows = ActWindow.search([
                    ('res_model', '=', 'electronic.mail'),
                    ('domain', '=', str([('mailbox', '=', mailbox.id)])),
                    ])
            actions = [a_w.action for a_w in act_windows]
            keywords = ActionKeyword.search([('action', 'in', actions)])
            menus = [k.model for k in keywords]
        if menus:
            cls.raise_user_error('menu_exist')
        data_menu_mailbox, = ModelData.search([
                ('module', '=', 'electronic_mail'),
                ('model', '=', 'ir.ui.menu'),
                ('fs_id', '=', 'menu_mail'),
                ])
        menu_mailbox, = Menu.search([
                ('id', '=', data_menu_mailbox.db_id)
                ])
        actions = Action.create([{
                    'name': mb.name,
                    'type': 'ir.action.act_window',
                    } for mb in mailboxes])
        act_windows = ActWindow.create([{
                    'res_model': 'electronic.mail',
                    'domain': encoder.encode([('mailbox', '=', mb.id)]),
                    'action': a.id,
                    }
                for mb in mailboxes for a in actions if a.name == mb.name])
        menus = Menu.create([{
                    'parent': menu_mailbox.id,
                    'name': mb.name,
                    'icon': 'tryton-list',
                    'active': True,
                    'sequence': 10,
                    } for mb in mailboxes])
        ActionKeyword.create([{
                    'model': 'ir.ui.menu,%s' % m.id,
                    'action': a_w.id,
                    'keyword': 'tree_open',
                    }
                for mb in mailboxes
                    for a_w in act_windows
                        for m in menus
                            if mb.id == eval(a_w.domain)[0][2]
                                and m.name == mb.name
                ])
        data_views = ModelData.search([
                ('module', '=', 'electronic_mail'),
                ('model', '=', 'ir.ui.view'),
                ['OR',
                    ('fs_id', '=', 'mail_view_tree'),
                    ('fs_id', '=', 'mail_view_form'),
                    ],
                ])
        views = View.search([('id', 'in', [v.db_id for v in data_views])])
        ActWindowView.create([{
                    'act_window': a_w.id,
                    'view': v.id,
                    'sequence': 10 if v.type == 'tree' else 20,
                    } for a_w in act_windows for v in views])
        return 'reload menu'


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
    _rec_name = 'subject'
    mailbox = fields.Many2One('electronic.mail.mailbox', 'Mailbox',
        required=True)
    from_ = fields.Char('From')
    sender = fields.Char('Sender')
    to = fields.Char('To')
    cc = fields.Char('CC')
    bcc = fields.Char('BCC')
    subject = fields.Char('Subject')
    date = fields.DateTime('Date')
    body_html = fields.Function(fields.Text('Body HTML'), 'get_email')
    body_plain = fields.Function(fields.Text('Body Plain'), 'get_email')
    deliveredto = fields.Char('Deliveret-To')
    reference = fields.Char('References')
    reply_to = fields.Char('Reply-To')
    num_attach = fields.Function(fields.Integer('Number of attachments'),
        'get_email')
    message_id = fields.Char('Message-ID', help='Unique Message Identifier')
    in_reply_to = fields.Char('In-Reply-To')
    digest = fields.Char('MD5 Digest', size=32)
    collision = fields.Integer('Collision')
    email_file = fields.Function(fields.Binary('Email File'), 'get_email',
        setter='set_email')
    flag_send = fields.Boolean('Sent', readonly=True)
    flag_received = fields.Boolean('Received', readonly=True)
    flag_seen = fields.Boolean('Seen')
    flag_answered = fields.Boolean('Answered')
    flag_flagged = fields.Boolean('Flagged')
    flag_draft = fields.Boolean('Draft')
    flag_recent = fields.Boolean('Recent')
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
    attempts = fields.Integer("Attempts", required=True, readonly=True)

    @classmethod
    def __setup__(cls):
        super(ElectronicMail, cls).__setup__()
        cls._order.insert(0, ('date', 'DESC'))
        cls._error_messages.update({
                'smtp_error': 'Error connecting to SMTP server. '
                    'Emails have not been sent: %s',
                'smtp_server_default': 'There are not default SMTP server',
                'email_invalid': ('Invalid email "%s".'),
                })

    @classmethod
    def __register__(cls, module_name):
        cursor = Transaction().cursor
        sql_table = cls.__table__()

        super(ElectronicMail, cls).__register__(module_name)

        # Migration from 3.2: fill required attempts
        cursor.execute(*sql_table.select(sql_table.id,
                where=(sql_table.attempts == None)))
        records_to_update = reduce_ids(sql_table.id,
            [v[0] for v in cursor.fetchall()])
        cursor.execute(*sql_table.update(
                columns=[sql_table.attempts], values=[0],
                where=(records_to_update)))

    @staticmethod
    def default_attempts():
        return 0

    @classmethod
    def validate(cls, emails):
        super(ElectronicMail, cls).validate(emails)
        if CHECK_EMAIL:
            for email in emails:
                if email.from_ and not check_email(parseaddr(email.from_)[1]):
                    cls.raise_user_error('email_invalid', (email.from_,))
                for recipient in email.recipients_from_fields():
                    if not check_email(parseaddr(recipient)[1]):
                        cls.raise_user_error('email_invalid', (recipient,))

    def recipients_from_fields(self):
        """
        Returns a list of email addresses who are the recipients of this email

        :param email_record: Browse record of the email
        """
        recipients = []
        for field in ('to', 'cc', 'bcc'):
            if getattr(self, field, False):
                recipients.extend(
                    getattr(self,
                        field).replace(' ', '').replace(',', ';').split(';')
                    )
        return recipients

    @classmethod
    def send_emails_scheduler(cls, args=None):
        '''
        This method is intended to be called from ir.cron
        @param args: Tuple with a limit of emails sent by each call of the cron
        '''
        Mailbox = Pool().get('electronic.mail.mailbox')

        limit = None
        if args:
            try:
                limit = int(args)
            except (TypeError, ValueError):
                pass

        mailboxs = Mailbox.search([
            ('scheduler', '=', True),
            ])
        if not mailboxs:
            logger.warning('Configure mailboxs to send by the scheduler')
            return

        emails = cls.search([
            ('mailbox', 'in', mailboxs)
            ], order=[('date', 'ASC')], limit=limit)
        logger.info('Start send %s emails' % (len(emails)))
        return cls.send_emails(emails)

    @classmethod
    def send_emails(cls, emails):
        pool = Pool()
        EMailConfiguration = pool.get('electronic.mail.configuration')
        email_configuration = EMailConfiguration(1)
        sent_mailbox = email_configuration.sent

        grouped_emails = groupby(emails, operator.attrgetter('mailbox'))

        for mailbox, emails in grouped_emails:
            smtp_server = None
            if not mailbox.smtp_server:
                logger.error('Not configured SMTP server '
                    'in mailbox %s' % (mailbox.name))
                continue
            try:
                smtp_server = mailbox.smtp_server.get_smtp_server()
            except (error, gaierror, SMTPAuthenticationError), e:
                try:
                    cls.raise_user_error('smtp_error', error_args=(e,))
                except UserError:
                    logger.error('Messages not sent: %s' % (e,))
            else:
                for email in emails:
                    email.attempts += 1
                    try:
                        smtp_server.sendmail(email.from_,
                            email.recipients_from_fields(), email._get_email())
                    except SMTPException, e:
                        logger.error('Messages not sent: %s' % (e,))
                    else:
                        logger.info('Send email: %s' % email.rec_name)
                        email.mailbox = sent_mailbox
                        email.flag_send = True
                    finally:
                        email.save()
            finally:
                smtp_server.quit()

    def send_email(self):
        pool = Pool()
        SMTP = pool.get('smtp.server')
        EmailConfiguration = pool.get('electronic.mail.configuration')
        email_configuration = EmailConfiguration(1)

        recipients = self.recipients_from_fields()
        if not recipients:
            self.mailbox = email_configuration.draft
            self.save()
            return False

        if self.mailbox.smtp_server:
            server = self.mailbox.smtp_server
        elif email_configuration.sent and email_configuration.sent.smtp_server:
            server = email_configuration.sent.smtp_server
        else:
            servers = SMTP.search([
                    ('state', '=', 'done'),
                    ('default', '=', True),
                    ], limit=1)
            if not servers:
                self.raise_user_error('smtp_server_default')
            server, = servers

        try:
            smtp_server = server.get_smtp_server()
            smtp_server.sendmail(self.from_, recipients, self._get_email())
            smtp_server.quit()
            self.flag_send = True
            self.save()
        except (error, gaierror, SMTPAuthenticationError), e:
            try:
                self.raise_user_error('smtp_error',
                    error_args=(e,))
            except UserError:
                logger.error(' Message not sent: %s' % (e,))
                return False
        return True

    @property
    def all_to(self):
        email = msg_from_string(self.email_file)
        parse_all_to = []
        if email:
            all_to = getaddresses(email.get_all('to', []))
            for to in all_to:
                parse_all_to.append((_decode_header(to[0]), _decode_header(to[1])))
        return parse_all_to

    @property
    def all_cc(self):
        email = msg_from_string(self.email_file)
        parse_all_cc = []
        if email:
            all_cc = getaddresses(email.get_all('cc', []))
            for cc in all_cc:
                parse_all_cc.append((_decode_header(cc[0]), _decode_header(cc[1])))
        return parse_all_cc

    @property
    def all_bcc(self):
        email = msg_from_string(self.email_file)
        parse_all_bcc = []
        if email:
            all_bcc = getaddresses(email.get_all('bcc', []))
            for bcc in all_bcc:
                parse_all_bcc.append(
                    (_decode_header(bcc[0]), _decode_header(bcc[1])))
        return parse_all_bcc

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

    @classmethod
    def search_rec_name(cls, name, clause):
        return ['OR',
            ('subject',) + tuple(clause[1:]),
            ('from_',) + tuple(clause[1:]),
            ('to',) + tuple(clause[1:]),
            ('cc',) + tuple(clause[1:]),
            ('bcc',) + tuple(clause[1:]),
            ]

    @classmethod
    def get_rec_name(cls, records, name):
        if not records:
            return {}
        res = {}
        for mail in records:
            res[mail.id] = '%s (ID: %s)' % (mail.subject, mail.id)
        return res

    def get_body(self, msg):
        """Returns the email body
        """
        maintype_text = {
            'body_plain': "",
            'body_html': ""
        }
        maintype_multipart = maintype_text.copy()
        if msg:
            if not msg.is_multipart():
                decode_body = _decode_body(msg)
                if msg.get_content_subtype() == "html":
                    maintype_text['body_html'] = decode_body
                else:
                    maintype_text['body_plain'] = decode_body
            else:
                for part in msg.walk():
                    maintype = part.get_content_maintype()
                    if maintype == 'text':
                        decode_body = _decode_body(part)
                        if part.get_content_subtype() == "html":
                            maintype_text['body_html'] = decode_body
                        else:
                            maintype_text['body_plain'] = decode_body
                    if maintype_text['body_plain'] and maintype_text['body_html']:
                        break
                    if maintype == 'multipart':
                        for p in part.get_payload():
                            if p.get_content_maintype() == 'text':
                                decode_body = _decode_body(p)
                                if p.get_content_subtype() == 'html':
                                    maintype_multipart['body_html'] = decode_body
                                else:
                                    maintype_multipart['body_plain'] = decode_body
                    elif maintype != 'multipart' and not part.get_filename():
                        decode_body = _decode_body(part)
                        if not maintype_multipart['body_plain']:
                            maintype_multipart['body_plain'] = decode_body
                        if not maintype_multipart['body_html']:
                            maintype_multipart['body_html'] = decode_body
                if not maintype_text['body_plain']:
                    maintype_text['body_plain'] = maintype_multipart['body_plain']
                if not maintype_text['body_html']:
                    maintype_text['body_html'] = maintype_multipart['body_html']
        return maintype_text

    @staticmethod
    def get_attachments(msg):
        attachments = []
        if msg:
            counter = 1
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                if part.get('Content-Disposition') is None:
                    continue
                if part.get_filename():
                    filename = part.get_filename()
                    if not filename:
                        ext = mimetypes.guess_extension(part.get_content_type())
                        if not ext:
                            # Use a generic bag-of-bits extension
                            ext = '.bin'
                        filename = 'part-%03d%s' % (counter, ext)
                    counter += 1

                    data = part.get_payload(decode=True)
                    content_type = part.get_content_type()
                    if not data:
                        continue
                    attachments.append({
                            'filename': filename,
                            'data': data,
                            'content_type': content_type,
                            })
        return attachments

    @classmethod
    def get_mailbox_owner(cls, records, name):
        "Returns owner of mailbox"
        mails = records
        return dict([(mail.id, mail.mailbox.user.id) for mail in mails])

    @classmethod
    def get_mailbox_users(cls, records, names):
        res = {}
        for name in names:
            assert name in ('mailbox_read_users', 'mailbox_write_users')
            for mail in records:
                res[name][mail.id] = [x.id for x in mail.mailbox[name[8:]]]
        return res

    @classmethod
    def search_mailbox_owner(cls, name, clause):
        return [('mailbox.user',) + clause[1:]]

    @classmethod
    def search_mailbox_users(cls, name, clause):
        return [('mailbox.' + name[8:],) + clause[1:]]

    def _get_email(self):
        """
        Returns the email object from reading the FS
        :param electronic_mail: Browse Record of the mail
        """
        db_name = Transaction().cursor.dbname
        value = u''
        if self.digest:
            filename = self.digest
            if self.collision:
                filename = filename + '-' + str(self.collision)
            filename = os.path.join(config.get('database', 'path'),
                db_name, 'email', filename[0:2], filename)
            try:
                with open(filename, 'rb') as file_p:
                    value = fields.Binary.cast(file_p.read())
            except IOError:
                pass
        return value

    @classmethod
    def get_email(cls, mails, names):
        result = {}
        for fname in ['body_plain', 'body_html', 'num_attach', 'email_file']:
            result[fname] = {}
        for mail in mails:
            email_file = mail._get_email() or None
            result['email_file'][mail.id] = (fields.Binary.cast(email_file)
                if email_file else None)
            email = msg_from_string(email_file)
            body = cls.get_body(mail, email)
            result['body_plain'][mail.id] = body.get('body_plain')
            result['body_html'][mail.id] = body.get('body_html')
            result['num_attach'][mail.id] = len(cls.get_attachments(email))
        for fname in ['body_plain', 'body_html', 'num_attach', 'email_file']:
            if fname not in names:
                del result[fname]
        return result

    @classmethod
    def set_email(cls, records, name, data):
        """Saves an email to the data path

        :param data: Email as string
        """
        if data is False or data is None:
            return
        db_name = Transaction().cursor.dbname
        # Prepare Directory <DATA PATH>/<DB NAME>/email
        directory = os.path.join(config.get('database', 'path'), db_name)
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
    def create_from_email(cls, mail, mailbox, context={}):
        """
        Creates a mail record from a given mail
        :param mail: Email
        :param mailbox: Mailbox
        :param context: dict
        """
        email_date = (_decode_header(mail.get('date', "")) and
            datetime.fromtimestamp(
                mktime(parsedate(mail.get('date')))))
        if not mailbox:
            logger.error('Not mailbox configured.')
            return

        values = {
            'mailbox': mailbox.id,
            'from_': _decode_header(mail.get('from')),
            'sender': _decode_header(mail.get('sender')),
            'to': _decode_header(mail.get('to')),
            'cc': _decode_header(mail.get('cc')),
            'bcc': context.get('bcc'),
            'subject': _decode_header(mail.get('subject')),
            'date': email_date,
            'message_id': _decode_header(mail.get('message-id')),
            'in_reply_to': _decode_header(mail.get('in-reply-to')),
            'deliveredto': _decode_header(mail.get('delivered-to')),
            'reference': _decode_header(mail.get('references')),
            'reply_to': _decode_header(mail.get('reply-to')),
            'email_file': mail.as_string(),
            'size': getsizeof(mail.as_string()),
            }

        email = cls.create([values])[0]
        return email

    @classmethod
    def validate_emails(cls, emails):
        '''Validate Emails is a email
        :param emails: list strings
        '''
        if CHECK_EMAIL:
            for email in emails:
                if not check_email(parseaddr(email)[1]):
                    cls.raise_user_error('email_invalid', error_args=(email,))
        return True
