"""
Publisher class for RabbitMQ queue
"""

import pika
import xfc_control.scripts.config as CFG
import json


class RabbitMQPublisher:

    def __init__(self, queue_name: str = "publisher"):
        # Load the config and extract the rabbit config
        self.config = CFG.load_config()
        self.rabbit_config = self.config[CFG.RABBIT_CONFIG_SECTION]
        self.queue_name = queue_name
        self.queue_config = CFG.get_queue_config(
            self.config,
            self.queue_name,
        )
        self.channel = None
        self.logger = None

    def connect(self) -> None:
        """Connect to the RabbitMQ using the info in the config, and the queue name."""
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    self.rabbit_config[CFG.RABBIT_SERVER],
                    credentials=pika.PlainCredentials(
                        self.rabbit_config[CFG.RABBIT_USER],
                        self.rabbit_config[CFG.RABBIT_PASSWORD],
                    ),
                    virtual_host=self.rabbit_config[CFG.RABBIT_VHOST],
                    heartbeat=self.rabbit_config[CFG.RABBIT_HEARTBEAT],
                    blocked_connection_timeout=self.rabbit_config[CFG.RABBIT_TIMEOUT],
                )
            )
        except Exception as e:
            msg = (
                f"Cannot connect to RabbitMQ server "
                f"{self.rabbit_config[CFG.RABBIT_SERVER]} "
                f"with user: {self.rabbit_config[CFG.RABBIT_USER]} "
                f"vhost: {self.rabbit_config[CFG.RABBIT_VHOST]}. "
                f"Reason: {e}"
            )
            self.logger.critical(msg)
            raise RuntimeError(f"ERROR - {msg}")
        else:
            self.logger.info(
                (
                    f"Connected to RabbitMQ server "
                    f"{self.rabbit_config[CFG.RABBIT_SERVER]} "
                    f"with user: {self.rabbit_config[CFG.RABBIT_USER]} "
                    f"vhost: {self.rabbit_config[CFG.RABBIT_VHOST]}"
                ),
            )

        self.channel = connection.channel()
        self.declare_queue()
        self.declare_bindings()

    def close(self) -> None:
        """Close the channel"""
        self.logger.info("Closing RabbitMQ connection")
        self.channel.close()

    def setup_logging(self, process_name: str) -> None:
        """Create and setup logging."""
        self.logger = CFG.setup_logging(
            config=self.config,
            process_name=process_name,
        )

    def attach_logger(self, logger) -> None:
        """Attach a logger if one has already been created."""
        self.logger = logger

    def declare_queue(self) -> None:
        """Declare a queue on the rabbit server, using the info in the config"""
        # Declare queue
        try:
            self.channel.queue_declare(
                queue=self.queue_name,
                durable=True,
                arguments={
                    "x-queue-type": self.queue_config[CFG.RABBIT_QUEUE_TYPE],
                },
            )
        except Exception as e:
            msg = (
                f"Cannot declare queue name: {self.queue_name} with type: "
                f"{self.queue_config[CFG.RABBIT_QUEUE_TYPE]}. "
                f"Reason: {e}"
            )
            self.logger.critical(msg)
            raise RuntimeError(f"ERROR - {msg}")
        else:
            self.logger.info(f"Declared queue: {self.queue_name}")

    def declare_bindings(self):
        """
        Declare binding to an exchange on the rabbit server, using the info in the
        config.
        """
        exchange_name = self.rabbit_config[CFG.RABBIT_EXCHANGE_NAME]
        try:
            self.channel.exchange_declare(
                exchange=exchange_name,
                exchange_type=self.rabbit_config[CFG.RABBIT_EXCHANGE_TYPE],
            )
        except Exception as e:
            msg = f"Could not declare exchange: {exchange_name}. Reason: {e}"
            self.logger.critical(msg)
        else:
            self.logger.info(f"Declared exchange: {exchange_name} ")

        # Bind the queue to the exchange and routing key
        try:
            self.channel.queue_bind(
                exchange=exchange_name,
                queue=self.queue_name,
                routing_key=self.queue_config[CFG.RABBIT_QUEUE_NAME],
            )
        except Exception as e:
            msg = (
                f"Could not bind queue: {self.queue_name} to exchange: ",
                f"{exchange_name}. Reason: {e}",
            )
            self.logger.critical(msg)
            raise RuntimeError(f"ERROR - {msg}")
        else:
            self.logger.info(
                f"Bound queue: {self.queue_name} to exchange: {exchange_name}"
            )

    def publish_message(
        self,
        message: dict,
    ) -> None:
        """Publish a message to an exchange on the rabbit server"""
        properties = pika.BasicProperties(
            content_encoding="application/json",
            delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE,
        )
        try:
            self.channel.basic_publish(
                exchange=self.rabbit_config[CFG.RABBIT_EXCHANGE_NAME],
                properties=properties,
                routing_key=self.queue_config[CFG.RABBIT_RK],
                body=json.dumps(message),
            )
        except Exception as e:
            msg = (
                "Could not publish message with routing key: "
                f"{self.queue_config[CFG.RABBIT_RK]} "
                f"to exchange: {self.rabbit_config[CFG.RABBIT_EXCHANGE_NAME]}. "
                f"Reason: {e}"
            )
            self.logger.critical(msg)
            raise RuntimeError(f"ERROR - {msg}")
        else:
            self.logger.info(
                (
                    f"Published message with routing key: "
                    f"{self.queue_config[CFG.RABBIT_RK]} "
                    f"to exchange: {self.rabbit_config[CFG.RABBIT_EXCHANGE_NAME]}"
                ),
            )
