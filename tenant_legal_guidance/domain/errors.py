class DomainError(Exception):
    """Base for domain-level errors."""


class ResourceNotFound(DomainError):
    pass


class ValidationFailed(DomainError):
    pass


class ConflictError(DomainError):
    pass


class ServiceUnavailable(DomainError):
    pass


