Electronic Mail Module
######################

The Electronic Mail module defines the base Mailbox and Emails.

Configuration:
**************

In your configuration Tryton server file, configure:

- smtp_server
- smtp_port
- smtp_ssl
- smtp_tls
- smtp_password
- smtp_user
- data_path

Mailbox:
********

Virtual directories where parent email (categorization)

Electronic Mail:
****************

Email information.

Data email is save in directory server defined in data_path configuration:

<DATA PATH>/<DB NAME>/email
