from __future__ import annotations


class AppError(Exception):
    """An error the user can understand. `code` is translated by the UI."""

    def __init__(self, code: str, message: str = "", status: int = 400, **details):
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status = status
        self.details = details

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, "details": self.details}
