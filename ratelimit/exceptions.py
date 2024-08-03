class BaseBackendException(Exception):
    """
    Base class for exception raised by Backends
    """

    pass


class BackendConnectionException(BaseBackendException):
    """
    Backend exception for ConnectionError
    """

    pass
