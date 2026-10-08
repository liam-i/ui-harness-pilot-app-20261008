"""Stable diagnostic codes shared by the library and its thin CLI."""


class CheckError(ValueError):
    def __init__(self, code, message, source="", location=""):
        super().__init__(message)
        self.diagnostic = dict(code=code, message=message, source=str(source), location=location)


def require(condition, code, message, source="", location=""):
    if not condition:
        raise CheckError(code, message, source, location)
