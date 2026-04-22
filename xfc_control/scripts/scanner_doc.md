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