EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_LIMIT = 3


class BoxError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = EXIT_ERROR, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = details

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, **self.details}
