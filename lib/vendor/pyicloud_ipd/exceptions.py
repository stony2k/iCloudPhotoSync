"""pyicloud_ipd exceptions — simplified from icloudpd v1.32.2."""


class PyiCloudException(Exception):
    """Generic iCloud exception."""
    pass


class PyiCloudAPIResponseException(PyiCloudException):
    """iCloud response exception."""

    def __init__(self, reason, code=None):
        self.reason = reason
        self.code = code
        message = reason or ""
        if code:
            message += " (%s)" % code
        super().__init__(message)


class PyiCloudServiceNotActivatedException(PyiCloudAPIResponseException):
    pass


class PyiCloudServiceUnavailableException(PyiCloudException):
    pass


class PyiCloudConnectionException(PyiCloudException):
    pass


class PyiCloudFailedLoginException(PyiCloudException):
    pass


class PyiCloud2SARequiredException(PyiCloudException):
    def __init__(self, apple_id):
        message = "Two-step authentication required for account: %s" % apple_id
        super().__init__(message)
