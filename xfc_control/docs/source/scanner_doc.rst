XFC RabbitMQ Scanner Setup & Usage
==================================

XFC now uses RabbitMQ queues and 3 processes to schedule, perform and process the scanning of the XFC volumes.

The queues are:

* xfc_publish_scan
* xfc_consume_scan

The processes are run using ``./manage.py runscript <process name>`` and are:

* xfc_queue_scans - place messages into the ``xfc_publish_scan`` queue to schedule scans.
* xfc_scan - consume a message from the ``xfc_publish_scan`` queue and perform the scan, put a message into the ``xfc_consume_scan`` queue when finished.
* xfc_process_scan - consume a message from the ``xfc_consume_scan`` queue and update the database with the scan details.

Additionally there is an administration process:

* xfc_fix_quotas - recalculate all the user quotas based on the scans.


xfc_queue_scans
---------------

To publish messages on the ``xfc_publish_scan`` queue, use the ``xfc_queue_scans`` script.  This takes an argument, which has to be one of:

* ``one_user`` - queue a single scan for a single user.  This will be the user whose directory was scanned the furthest in the past.
* ``all_users`` - queue multiple scans, one for each user.
* ``all_vols`` - queue multiple scans, one for each volume.
* ``user <user_name>`` - queue a single scan for a named user.

This script must be run with ``./manage.py``.  It is a single-shot script so, in production, should be run in a scheduling service, like ``cron`` or ``circusd``.
Examples of usage:

* ``./manage.py runscript xfc_publish_scan --script-args=one_user``
* ``./manage.py runscript xfc_publish_scan --script-args=all_users``
* ``./manage.py runscript xfc_publish_scan --script-args=all_vols``
* ``./manage.py runscript xfc_publish_scan --script-args=user nrmassey``

xfc_scan
--------

This process performs the actual scan by consuming a message from the ``xfc_publish_scan`` queue, performing a ``du`` (or similar command) on the user's cache directory to determine the amount of data used and then publishing the result to the ``xfc_consume_scan`` queue.

This process runs in a loop and so should be started via a scheduling service like circusd or supervisord.

To run in test:

* ``./manage.py runscript xfc_scan``

xfc_process_scan
----------------

This process consumes a message from the ``xfc_consume_scan`` queue, which will contain a scan for a single user and their cache directory, and updates the database with that scan.  It then calculates the user's total and temporal quota and updates the database with those values.  If a user is over their quota, it will send an email informing them of this.

This process runs in a loop and so should be started via a scheduling service like circusd or supervisord.

To run in test:

* ``./manage.py runscript xfc_process_scan``