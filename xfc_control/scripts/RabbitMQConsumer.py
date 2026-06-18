"""
Consumer class for RabbitMQ queue.  Inherits from publisher class
"""

from xfc_control.scripts.RabbitMQPublisher import RabbitMQPublisher


class RabbitMQConsumer(RabbitMQPublisher):
    def __init__(self, queue_name: str = "consumer"):
        super().__init__(queue_name)

    def start_consuming(self, callback: function):
        """Simple function to start consuming from the Rabbit queue"""
        try:
            self.channel.basic_consume(
                queue=self.queue_name,
                on_message_callback=callback,
                auto_ack=False,
            )
            self.channel.start_consuming()
        except Exception as e:
            msg = f"Could not start consumer for Queue: {self.queue_name} Reason {e}"
            self.log("critical", msg)
            raise RuntimeError(f"ERROR - {msg}")
        else:
            self.log("info", f"Started consumer for Queue: {self.queue_name}")
