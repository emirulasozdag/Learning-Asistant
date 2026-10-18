import re

from app.retrieval.types import RetrievedPassage

_LABEL = re.compile(r"\[(S\d+)\]")


def resolve_citations(
    answer: str, cited_labels: list[str], labels: dict[str, RetrievedPassage]
) -> tuple[str, list[RetrievedPassage]]:
    """Modelin kullandığı [S#] etiketlerini doğrular ve numaralandırır.

    - Getirilmemiş (bilinmeyen) etiketler atılır; metindeki işaretleri de silinir.
    - Geçerli etiketler ilk geçtikleri sırayla [1], [2]... olarak yeniden numaralanır.
    - Dönen liste boşsa cevap hiçbir kaynağa dayandırılamamıştır; çağıran reddetmelidir.
    """
    order: list[str] = []
    for label in [*_LABEL.findall(answer), *cited_labels]:
        if label in labels and label not in order:
            order.append(label)

    numbers = {label: index for index, label in enumerate(order, start=1)}

    def renumber(match: re.Match[str]) -> str:
        number = numbers.get(match.group(1))
        return f"[{number}]" if number else ""

    # Silinen etiketlerin bıraktığı çift boşlukları topla; içeriğin geri kalanına dokunma.
    text = re.sub(r"(?<=\S) {2,}(?=\S)", " ", _LABEL.sub(renumber, answer)).strip()
    return text, [labels[label] for label in order]
