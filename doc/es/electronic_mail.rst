===========================
Correo electrónico saliente
===========================

.. inheritref:: electronic_mail/electronic_mail:section:mailbox

MailBox
=======

Directorios virtuales donde se clasificarán los correos electrónicos.

.. inheritref:: electronic_mail/electronic_mail:section:electronic_email

Correo generado
===============

Dispone en el historial el correo electrónico enviado. El contenido del correo se
guardará en el directorio físico de la configuración del servidor:

.. code:: python

    <DATA PATH>/<DB NAME>/email

.. inheritref:: electronic_mail/electronic_mail:section:configuration

Configuración
=============

En el fichero de configuración del servidor de Tryton, se debe especificar la
variable:

.. code:: python

    data_path
