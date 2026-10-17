from dataclasses import dataclass
from typing import Literal

from app.retrieval.types import RetrievedPassage


@dataclass
class ClaimLabel:
    claim: str
    label: Literal["supported", "unsupported"]
    judge_model: str


def label_claims(claims: list[str], passages: list[RetrievedPassage]) -> list[ClaimLabel]:
    """Generator'dan farklı model ailesinden judge ile her iddiayı etiketle."""
    raise NotImplementedError
