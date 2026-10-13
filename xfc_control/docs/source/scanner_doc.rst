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

This process consumes a message from the ``xfc_consume_scan`` queue, which will contain a scan for a single user and their cache directory, and updates the database with that scan.  It then calculates the user's total and temporal quota and updates the database with those values.

This process runs in a loop and so should be started via a scheduling service like circusd or supervisord.

To run in test:

* ``./manage.py runscript xfc_process_scan``


How I run the rabbits mode for the scanner

1. Start RabbitMQ (Docker)::

    bash docker run -d
      --hostname rabbitmq
      --name rabbitmq
      -p 5672:5672
      -p 15672:15672
      rabbitmq:3-management

2. Install requirements: 
Make sure your venv has the required requirements (e.g. ``pika``, ``click``, Django project requirements).

3. Start the worker (consumer): 
Run from your Django project root::

    bash python manage.py runscript xfc_scan

* This starts the RabbitMQ consumer
* It will wait for scan jobs

4. Send a scan job (producer): 
In another terminal::

    bash python xfc_control/scripts/xfc_scan.py
      --path {target_dir}
      --email {user_email}
      --rabbit

* Sends a message to RabbitMQ
* Worker picks it up automatically
* Scan runs and results are stored in the database

CLI
===

There is a click version of that command which does not use rabbits that is formatted like this::

    bash python xfc_control/scripts/xfc_scan.py
      --path {target_dir}
      --email {user_email}
      -h (optional)

the only difference being the lack of ``--rabbit``

CLI options
-----------

Options::

      --path DIRECTORY
      --email TEXT      User email  [required]
      -h, --human       Human readable output
      --rabbit          Send to RabbitMQ instead of running locally
      --du
      --pdu
      --default
      --help            Show this message and exit.

selecting the du, pdu or default flag only selects the latest one in the line (so doing -du -pdu it would only use pdu)
These three flags determine the method of scanning::

    du takes ~330 seconds
    python takes ~20 seconds
    pdu takes ~10-15 seconds

The scanner will now run a quick command to check if pdu or du is on your file system and whether ``-b`` works. If pdu is not on your system, it uses du, if du is not on your system, it uses the python version.

if ``-b`` does not work then it will use ``-k`` and multiply by 1024 which is slightly more inaccurate but it is roughly the same

Scheduling scans
----------------

Building on Matteo's work, we have 3 phases to the scan:

1.  Choose which user to scan next, put a message in the Rabbit queue.  The next user to scan should be the one who was scanned last, but doesn't already have a message in the queue.  There is flexibility here as the admin can choose "all_users", "next_user" or "all_volumes". ``xfc_queue_scans.py``

2.  Perform a scan by taking the next scan off the queue, scan the user directory, and put the result onto the queue.  The admin can also run this from the command line (i.e. without needing a message to kick it off).  In this case they need to specify a user and a directory.  The result is still put back on the queue. ``xfc_scan.py``

3.  Process the scan by taking the result off the queue and updating the database for the user. ``xfc_process_scan.py``

Connecting to Rabbit
--------------------

* Declare exchange
* Connect to queue
* Need config in the django settings files 
* Follow NLDS config:


::

    "rabbitMQ": {
      "user" : "",
      "password": "",
      "server": "",
      "admin_port" : "",
      "vhost" : "",
      "exchange" : [
        {
          "name" : "xfc-dev",
          "type" : "classic"
        }
      ],
      "queues" : [
        {
          "name": "xfc_publish_scan",
          "bindings": [
            {
              "exchange": "xfc-dev",
            }
          ]
        },
        {
          "name": "xfc_consume_scan",
          "bindings": [
            {
              "exchange": "xfc-dev",
            }
          ]
        }
      ]
    }
