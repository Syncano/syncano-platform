class APNSException(Exception):
    pass


class APNSServerError(APNSException):
    DESCRIPTIONS = {
        0: 'No errors encountered',
        1: 'Processing error',
        2: 'Missing device token',
        3: 'Missing topic',
        4: 'Missing payload',
        5: 'Invalid token size',
        6: 'Invalid topic size',
        7: 'Invalid payload size',
        8: 'Invalid token',
        10: 'Shutdown',
    }

    def __init__(self, status, identifier):
        super().__init__(status, identifier)
        self.status = status
        self.identifier = identifier
        self.description = self.DESCRIPTIONS.get(self.status, 'None (unknown)')


class APNSDataOverflow(APNSException):
    pass


class APNSSocketError(APNSException):
    pass
