from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document
from app.db.text_search import ts_config
from app.retrieval.types import RetrievedPassage

# Sorunun anahtar kelimeleri: dersin FTS yapılandırmasıyla kök alınır; İngilizce ya da Türkçe
# stopword olan kelimeler atılır. Ders dili 'tr' olup materyal İngilizce olabilir (ya da tersi):
# o zaman "what/is/the" Türkçe yapılandırmada silinmez ve her parçayla eşleşirdi.
#
# Puan: parçada geçen anahtar kelimelerin IDF toplamı (ders içinde nadir kelime daha değerli;
# BM25'in terim frekansı olmayan hâli). "centralized" gibi ayırt edici bir kelime, her sayfada
# geçen "version control"dan ağır basar. Kapsama = parçadaki IDF / sorudaki toplam IDF; derste
# hiç geçmeyen kelimeler (ör. "quicksort") paydada kalır ve kapsamayı düşürür.
_SEARCH = text(
    """
    WITH words AS (
        SELECT DISTINCT unnest(d.lexemes) AS lexeme
        FROM ts_debug(CAST(:config AS regconfig), :query) AS d
        WHERE cardinality(d.lexemes) > 0
          AND to_tsvector('english', d.token) <> ''::tsvector
          AND to_tsvector('turkish', d.token) <> ''::tsvector
    ),
    weights AS (
        SELECT t.q, ln(1 + (n.total - df.n + 0.5) / (df.n + 0.5)) AS idf
        FROM (SELECT CAST(quote_literal(lexeme) AS tsquery) AS q FROM words) t
        CROSS JOIN (SELECT count(*) AS total FROM chunks WHERE course_id = :course_id) n
        CROSS JOIN LATERAL (
            -- Doğrudan tablodan: GIN indeksi (search_vector) ve ders indeksi kullanılabilir.
            SELECT count(*) AS n FROM chunks c
            WHERE c.course_id = :course_id AND c.search_vector @@ t.q
        ) df
    ),
    query_total AS (
        SELECT sum(idf) AS idf,
               CAST(string_agg(CAST(q AS text), ' | ') AS tsquery) AS any_word
        FROM weights
    )
    SELECT c.id, sum(w.idf) AS score, sum(w.idf) / qt.idf AS coverage
    FROM chunks c
    JOIN documents doc ON doc.id = c.document_id AND doc.course_id = :course_id
        AND doc.approved_at IS NOT NULL
    JOIN weights w ON c.search_vector @@ w.q
    CROSS JOIN query_total qt
    WHERE c.course_id = :course_id
    GROUP BY c.id, c.search_vector, qt.idf, qt.any_word
    ORDER BY score DESC, ts_rank(c.search_vector, qt.any_word, 1) DESC, c.id
    LIMIT :k
    """
)


def lexical_search(db: Session, course: Course, query: str, k: int) -> list[RetrievedPassage]:
    """PostgreSQL full-text arama (IDF ağırlıklı); ders filtresi her alt sorguda uygulanır.

    Bir anahtar kelimenin eşleşmesi parçayı aday yapar (öğrenci sorusu materyaldeki cümleyle
    birebir örtüşmez); sıralama ve kapsama yukarıdaki açıklamada.
    """
    scored = db.execute(
        _SEARCH,
        {"config": ts_config(course.language), "query": query, "course_id": course.id, "k": k},
    ).all()
    if not scored:
        return []
    rows = db.execute(
        select(Chunk, Document.title)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.id.in_([chunk_id for chunk_id, _, _ in scored]))
    ).all()
    by_id = {chunk.id: (chunk, title) for chunk, title in rows}
    passages = []
    for rank, (chunk_id, score, coverage) in enumerate(scored, start=1):
        chunk, title = by_id[chunk_id]
        passages.append(
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
                keyword_coverage=float(coverage),
            )
        )
    return passages
