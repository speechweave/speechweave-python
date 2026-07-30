from __future__ import annotations


class SpeechWeaveError(Exception):
	def __init__(
		self,
		message: str,
		status: int = 500,
		code: str | None = None,
		body=None,
		retry_after: int | None = None,
		error_type: str | None = None,
		param: str | None = None,
	):

		super().__init__(message)

		self.status = status
		self.code = code
		self.body = body
		self.retry_after = retry_after
		self.error_type = error_type
		self.param = param
