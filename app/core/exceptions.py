from fastapi import HTTPException, status


class AuthError(HTTPException):
    def __init__(self, detail: str = "Non authentifié"):
        super().__init__(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


class ForbiddenError(HTTPException):
    def __init__(self, detail: str = "Accès refusé"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class NotFoundError(HTTPException):
    def __init__(self, resource: str = "Ressource"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} introuvable",
        )


class ConflictError(HTTPException):
    def __init__(self, detail: str = "Conflit de données"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class PaymentError(HTTPException):
    def __init__(self, detail: str = "Erreur de paiement"):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
        )


class ValidationError(HTTPException):
    def __init__(self, detail: str = "Données invalides"):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class TenantError(HTTPException):
    def __init__(self, detail: str = "Tenant invalide ou non autorisé"):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
