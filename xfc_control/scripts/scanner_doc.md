## RabbitMQ Scanner Setup & Usage

How I run the rabbits mode for the scanner

### 1. Start RabbitMQ (Docker)

```bash
docker run -d \
  --hostname rabbitmq \
  --name rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  rabbitmq:3-management
```

---

### 2. Install requirements

Make sure your venv has the required requirements (e.g. `pika`, `click`, Django project requirements).

---

### 3. Start the worker (consumer)

Run from your Django project root:

```bash
python manage.py runscript xfc_scan
```

* This starts the RabbitMQ consumer
* It will wait for scan jobs

---

### 4. Send a scan job (producer)

In another terminal:

```bash
python xfc_control/scripts/xfc_scan.py \
  --path {target_dir} \
  --email {user_email} \
  --rabbit
```

* Sends a message to RabbitMQ
* Worker picks it up automatically
* Scan runs and results are stored in the database



---


## CLI

There is a click version of that command which does not use rabbits that is formatted like this:


```bash
python xfc_control/scripts/xfc_scan.py \
  --path {target_dir} \
  --email {user_email}
  -h (optional)
```

the only difference being the lack of --rabbit


### CLI options
```
Options:
  --path DIRECTORY
  --email TEXT      User email  [required]
  -h, --human       Human readable output
  --rabbit          Send to RabbitMQ instead of running locally
  --du
  --pdu
  --default
  --help            Show this message and exit.
```

selecting the du, pdu or default flag only selects the latest one in the line (so doing -du -pdu it would only use pdu)
These three flags determine the method of scanning
```
du takes ~330 seconds
python takes ~20 seconds
pdu takes ~10-15 seconds
```

The scanner will now run a quick command to check if pdu or du is on your file system and whether -b works. If pdu is not on your system, it uses du, if du is not on your system, it uses the python version.

if -b does not work then it will use -k and multiply by 1024 which is slightly more inaccurate but it is roughly the same

### Scheduling scans

Building on Matteo's work, we want to have 3 phases to the scan:

1.  Choose which user to scan next, put a message in the Rabbit queue.  The next user to scan should be the one who was scanned last, but doesn't already have a message in the queue.
  -> xfc_queue_next_scan.py
2.  Perform a scan by taking the next scan off the queue, scan the user directory, and put the result onto the queue
  -> xfc_scan.py
3.  Process the scan by taking the result off the queue and updating the database for the user
  -> xfc_process_scan.py


Declare exchange
Connect to queue
Need config in /etc/xfc_control/xfc_config.json
Follow NLDS config:

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