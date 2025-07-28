# XFC Update Plan

## What is XFC?

XFC is an area of working disk for JASMIN users, with a Django application that stores information about the users of XFC, the mountpoint of the disk they work on, their quotas and their files.

The Django application also performs some auditing of the files and, in its original specification, would delete files when the user has passed a quota.

See these pages for more information:

https://help.jasmin.ac.uk/docs/short-term-project-storage/xfc/

XFC is deployed on a JASMIN VM using an Ansible script.

## The problem(s)

Currently the only use for XFC is when a user instigates `xfc init`, which creates their working directory.
The other functions, such as the scan and the deletion, have been disabled, for these reasons:

- The scan takes a long time
- The scan doesn't always complete before the next one starts
- (IIRC) it tries to scan all the directories at once!
- The scan results in a large database of files
- The emails informing the user that their files will be deleted results in a panic!

## A major problem

During the migration to Rocky 9, the database of users got deleted!
We can reinstate the users by looking at the directories under `/work/xfc/vol*`
(`vol1` and `vol3` are to be retired)

## The plan

The general plan is to decouple the scan from the Django framework, and to reduce its footprint

- Don't store files in the database
- Don't delete files (at least at the moment) - turn it into a notification service
- Rewrite the scanner to work on a single user's work directory at once, as a command line program
  - `django-xfc_control/xfc_control/scripts/xfc_scan.py`
  - Convert to command-line script taking a directory and scanning below that. Use `click` for the command line interface.
    - See `nlds-client` in `cedadev` github for a complicated example of `click`. Other simpler examples might be in the `cedadev` github
  - Use the meta-data from the file, via `stat` in Python, to calculate the temporal quota (sum_of(time file is present \* file size)), as well as the hard quota (sum_of(file size))
  - Picks up a message from a RabbitMQ queue
  - Publishes a message on completion
  - Eventually containerise this so it runs on Kubernetes, but to start with we can just run on xfc2
- Set up a RabbitMQ virtual host to hold a queue / exchange
- Modify Django database so each user has a "last scanned" field
- Create a Django script that finds the last scanned work directory (i.e. furthest in the past)
  - Publish message to RabbitMQ queue
  - Scanner picks up message, scans work directory, and publishes message on completion
- Create a Django script that handles the completion message
  - Consumes a message from the queue
  - Updates user quotas in database
  - Updates last scanned date in database
  - Sends notification email to user if they are over quota

Development can take place on your laptop. I'd suggest using Docker desktop to create a Postgres database and set Django `settings.py` to use this.

## Tasks

0. Neil create Matteo an admin account on `xfc2.jasmin.ac.uk/admin`
1. Add all the mountpoints (`/work/xfc/vol?`) back into the database at `xfc2.jasmin.ac.uk/admin/xfc_control/cachedisk/`
2. `xfc init <your username>`
3. Add all the users back into database with their correct mount points, and a standard quota of 300TB (temporal), 40TB (hard)

## Progress as of 28 July 2025 (author Matteo Guarnaccia)

All the tasks outlined in the update plan have been completed, and have been tested / are working locally.

- User's can be added back into the database with `xfc_user_creation.py` - can be run via runscript

  - this will also add the mountpoints (`/work/xfc/vol#`) back into the cachedisk database.
  - the `base_path` variable would need to be changed appropiatley for non-local running of the script

- `last_scanned` datetime field added to database. This can be done on deployment by running (in order): - `python manage.py makemigrations` - `python manage.py migrate` \* This will default create a column with the date 1/1/1900

- New scanning logic with RabbitMQ
  - User's work directories can be scanned using click command line app, with --path and --username specified as args.
  - The following scripts have been written to encompass the new RabbitMQ logic:
    - `xfc_user_scan_sweep` - This gets the oldest `last_scanned` user and produces a message - It is set to run once every 10 min in a very simple loop - Not sure on if the dir to be scanned is correct - see file comments
    - `xfc_scan` - not only is a command line app, but will consume message from `xfc_user_scan_sweep` - calculates hard and temporal quota with stat on user dir - produces message with quota data and username
    - `xfc_consume_scan_output` - consumes message from `xfc_scan` - updates the user's quotas and last_scanned fields. - sends mail to user if exceeded quota \* NOTE - I was having trouble getting this to work in my testing, got `[MainThread] Error sending mail: [Errno 111] Connection refused`
      I copied the current implementation in `xfc_schedule`
    * To run the program, locally each script can be run with `python manage.py runscript <scriptname>` in the order above.
    * There are comments on each file about error handling - how to improve
    * This (I assume) needs to be reconfigured to run automatically - not using `runscript`
