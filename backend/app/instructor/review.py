from app.schemas.instructor import ReviewDecision


def apply_review(instructor_id: int, decision: ReviewDecision) -> None:
    """Eğitmen onayını / düzeltmesini kaydet ve ilgili içeriği güncelle."""
    raise NotImplementedError
