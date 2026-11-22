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
#
# Hız: "burayı anlamadım" sorusunda arama metni anın transkriptiyle büyür (50–150 kelime) ve
# binlerce parça aday olur. Bu yüzden (1) (parça, kelime) eşleşmeleri bir kez bulunur; belge
# sıklığı (IDF'nin n'i) da puan da bu listeden çıkar, kelime başına ikinci bir sayım yapılmaz;
# (2) gruplama dar satırlarla yapılır (parçanın tsvector'ü gruplamaya ve sıralamaya taşınmaz);
# (3) eşitlik bozucu ts_rank yalnızca k'ncı puana yetişen parçalarda hesaplanır. Sayım yine
# dersin bütün parçaları üzerindedir (onay/durum süzgeci yalnızca sonuçlara uygulanır).
_SEARCH = text(
    """
    WITH words AS (
        SELECT DISTINCT unnest(d.lexemes) AS lexeme
        FROM ts_debug(CAST(:config AS regconfig), :query) AS d
        WHERE cardinality(d.lexemes) > 0
          AND to_tsvector('english', d.token) <> ''::tsvector
          AND to_tsvector('turkish', d.token) <> ''::tsvector
    ),
    any_word AS (
        SELECT CAST(string_agg(CAST(CAST(quote_literal(lexeme) AS tsquery) AS text), ' | ')
                    AS tsquery) AS q
        FROM words
    ),
    matches AS MATERIALIZED (
        -- Kelime başına GIN indeksi (search_vector) taraması; yalnızca dar sütunlar taşınır.
        SELECT c.id, c.document_id, w.lexeme
        FROM words w
        JOIN chunks c ON c.search_vector @@ CAST(quote_literal(w.lexeme) AS tsquery)
        WHERE c.course_id = :course_id
    ),
    weights AS (
        SELECT w.lexeme,
               ln(1 + (n.total - coalesce(df.n, 0) + 0.5) / (coalesce(df.n, 0) + 0.5)) AS idf
        FROM words w
        CROSS JOIN (SELECT count(*) AS total FROM chunks WHERE course_id = :course_id) n
        LEFT JOIN (SELECT lexeme, count(*) AS n FROM matches GROUP BY lexeme) df
            ON df.lexeme = w.lexeme
    ),
    scored AS (
        SELECT m.id, sum(w.idf) AS score
        FROM matches m
        JOIN weights w ON w.lexeme = m.lexeme
        JOIN documents doc ON doc.id = m.document_id AND doc.course_id = :course_id
            AND doc.approved_at IS NOT NULL AND doc.status = 'ready'
        GROUP BY m.id
    ),
    cutoff AS (
        -- k'ncı en yüksek puan: eşitlik bozucu (ts_rank) yalnızca bu puana yetişenlerde hesaplanır.
        SELECT min(score) AS score FROM (SELECT score FROM scored ORDER BY score DESC LIMIT :k) t
    )
    SELECT s.id, s.score, s.score / (SELECT sum(idf) FROM weights) AS coverage
    FROM scored s
    JOIN chunks c ON c.id = s.id
    CROSS JOIN any_word a
    WHERE s.score >= (SELECT score FROM cutoff)
    ORDER BY s.score DESC, ts_rank(c.search_vector, a.q, 1) DESC, s.id
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
