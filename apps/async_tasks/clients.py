# coding=UTF8
import uuid


class WebSocketClient:
    def __init__(self, request, fd, send_event, send_queue, recv_event,
                 recv_queue, timeout=5):
        self.request = request
        self.fd = fd
        self.send_event = send_event
        self.send_queue = send_queue
        self.recv_event = recv_event
        self.recv_queue = recv_queue
        self.timeout = timeout
        self.id = str(uuid.uuid1())
        self.connected = True

    def send(self, msg):
        self.send_queue.put(msg)
        self.send_event.set()

    def receive(self):
        return self.recv_queue.get()

    def close(self):
        self.connected = False
