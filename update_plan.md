XFC Update Plan
===============

What is XFC?
------------
XFC is an area of working disk for JASMIN users, with a Django application that stores information about the users of XFC, the mountpoint of the disk they work on, their quotas and their files.

The Django application also performs some auditing of the files and, in its original specification, would delete files when the user has passed a quota.

See these pages for more information:

https://help.jasmin.ac.uk/docs/short-term-project-storage/xfc/

XFC is deployed on a JASMIN VM using an Ansible script.

The problem(s)
--------------

Currently the only use for XFC is when a user instigates `xfc init`, which creates their working directory.
The other functions, such as the scan and the deletion, have been disabled, for these reasons:

* The scan takes a long time
* The scan doesn't always complete before the next one starts
* (IIRC) it tries to scan all the directories at once!
* The scan results in a large database of files
* The emails informing the user that their files will be deleted results in a panic!

A major problem
---------------

During the migration to Rocky 9, the database of users got deleted!
We can reinstate the users by looking at the directories under `/work/xfc/vol*`
(`vol1` and `vol3` are to be retired)

The plan
--------

The generak plan is to decouple the scan from the Django framework, and to reduce its footprint

* Don't store files in the database
* Don't delete files (at least at the moment) - turn it into a notification service
* Rewrite the scanner to work on a single user's work directory at once, as a command line program
  * Use the meta-data from the file, via `stat` in Python, to calculate the temporal quota, as well as the hard quota
  * Picks up a message from a RabbitMQ queue
  * Publishes a message on completion
  * Eventually containerise this so it runs on Kubernetes, but to start with we can just run on xfc2
* Set up a RabbitMQ virtual host to hold a queue / exchange
* Modify Django database so each user has a "last scanned" field
* Create a Django script that finds the last scanned work directory (i.e. furthest in the past)
  * Publish message to RabbitMQ queue
  * Scanner picks up message, scans work directory, and publishes message on completion
* Create a Django script that handles the completion message
  * Consumes a message from the queue
  * Updates user quotas in database
  * Updates last scanned date in database
  * Sends notification email to user if they are over quota

Development can take place on your laptop.  I'd suggest using Docker desktop to create a Postgres database and set Django `settings.py` to use this.