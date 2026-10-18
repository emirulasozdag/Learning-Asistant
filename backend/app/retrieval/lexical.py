from sqlalchemy import Text, cast, func, literal, select
from sqlalchemy.dialects.postgresql import REGCONFIG, TSQUERY
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document
from app.db.text_search import ts_config
from app.retrieval.types import RetrievedPassage


def lexical_search(db: Session, course: Course, query: str, k: int) -> list[RetrievedPassage]:
    """PostgreSQL full-text arama; ders filtresi sorgunun içinde uygulanır.

    Soru kökleri VEYA ile aranır (öğrenci sorusu, materyaldeki cümleyle birebir örtüşmez);
    sıralamayı `ts_rank_cd` yapar: daha çok ve daha yakın eşleşen parça üste çıkar.
    """
    config = cast(literal(ts_config(course.language)), REGCONFIG)
    # plainto_tsquery kökleri '&' ile bağlar; '|' yapınca tek bir kökün eşleşmesi yeter.
    tsquery = cast(func.replace(cast(func.plainto_tsquery(config, query), Text), "&", "|"), TSQUERY)
    rank = func.ts_rank_cd(Chunk.search_vector, tsquery).label("rank")
    rows = db.execute(
        select(Chunk, Document.title, rank)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.course_id == course.id, Chunk.search_vector.op("@@")(tsquery))
        .order_by(rank.desc(), Chunk.id)
        .limit(k)
    )
    return [
        RetrievedPassage(
            source_id=str(chunk.id),
            document_id=chunk.document_id,
            document_title=title,
            text=chunk.text,
            score=float(score),
            page=chunk.page,
            t_start=chunk.t_start,
            t_end=chunk.t_end,
            lexical_rank=rank,
        )
        for rank, (chunk, title, score) in enumerate(rows, start=1)
    ]
