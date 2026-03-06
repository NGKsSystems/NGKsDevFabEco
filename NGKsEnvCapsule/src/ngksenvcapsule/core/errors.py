from __future__ import annotations


class CapsuleError(Exception):
    exit_code = 10


class ConfigError(CapsuleError):
    exit_code = 2


class MissingRequiredError(CapsuleError):
    exit_code = 3


class VerifyFailedError(CapsuleError):
    exit_code = 4


class InternalError(CapsuleError):
    exit_code = 10
