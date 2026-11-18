from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schemas.common import DbId

# Sınırlar değerlendiriciye giden istem ve saklanan kayıt büyümesin diye (#15).
MAX_CRITERIA = 10
MAX_SOURCES = 20


class RubricCriterion(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    points: float = Field(gt=0, le=100)


class RubricIn(BaseModel):
    """Eğitmenin girdiği rubrik + referans cevap. Bir soruya veya bir kavrama bağlanır.

    Soruya bağlanırsa (`practice_item_id`) o sorunun üretilmiş rubriğinin yerine geçer ve açık
    uçlu cevaplar artık bununla değerlendirilir. Çoktan seçmeli sorular cevap anahtarıyla
    değerlendirilir; onlara rubrik girilmez (422).
    """

    concept: str = Field(min_length=1, max_length=300)
    reference_answer: str = Field(min_length=1, max_length=4000)
    criteria: list[RubricCriterion] = Field(min_length=1, max_length=MAX_CRITERIA)
    practice_item_id: DbId | None = None
    # Dersin onaylı materyalindeki parçalar; boşsa soruya bağlı rubrikte sorunun parçası kullanılır.
    source_ids: list[Annotated[str, Field(max_length=32)]] = Field(
        default=[], max_length=MAX_SOURCES
    )


class Rubric(RubricIn):
    id: int
    course_id: int
    # "generated": soruyla birlikte üretildi; "instructor": eğitmen girdi (girilince onaylıdır).
    origin: Literal["generated", "instructor"]
    approved: bool = False
