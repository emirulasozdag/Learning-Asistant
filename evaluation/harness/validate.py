"""Gold set ve envanteri doğrular; baseline için eksikleri listeler.

Kullanım (evaluation/ içinden):

    python -m harness.validate gold_sets/BLM2512/gold_set.json

Şema hatası → çıkış kodu 1. Şema geçerli ama eksik var (ör. 30'dan az incelenmiş soru) →
eksikler yazdırılır, çıkış kodu 0; `--strict` ile 2.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from harness.schemas import CorpusManifest, GoldSet, ItemKind, Split, load_gold_set, load_manifest

# Baseline'ın kabul edilebilir sayılması için gereken en az gerçek örnek (issue #8).
MIN_REVIEWED_ANSWERABLE = 30
MIN_OUT_OF_SCOPE = 30


def structural_errors(gold: GoldSet, manifest: CorpusManifest) -> list[str]:
    """Koşuyu geçersiz kılan tutarsızlıklar: koşucu bunlardan biri varsa çalışmaz."""
    errors: list[str] = []
    if gold.course_code.upper() != manifest.course_code.upper():
        errors.append(f"Ders kodu farklı: gold {gold.course_code}, envanter {manifest.course_code}")
    approved = manifest.approved_hashes()
    excluded = manifest.excluded_hashes()
    for item in gold.items:
        for locator in item.evidence:
            if locator.document_sha256 in excluded:
                errors.append(f"{item.id}: kanıt dışlanmış bir dokümanda")
            elif locator.document_sha256 not in approved:
                errors.append(f"{item.id}: kanıt envanterde olmayan bir dokümanda")
    questions = Counter(item.question.strip().casefold() for item in gold.items)
    for question, count in questions.items():
        if count > 1:
            errors.append(f"Aynı soru {count} kez: {question[:60]}")
    by_split: dict[Split, set[str]] = {s: set() for s in Split}
    for item in gold.items:
        by_split[item.split].add(item.question.strip().casefold())
    if by_split[Split.CALIBRATION] & by_split[Split.HELDOUT]:
        errors.append("Aynı soru hem kalibrasyon hem held-out setinde")
    return errors


def item_gaps(gold: GoldSet) -> list[str]:
    """Tek tek sorulardaki eksikler; koşu sürer ama metriklerin paydası küçülür."""
    gaps: list[str] = []
    for item in gold.items:
        if item.kind is ItemKind.ANSWERABLE:
            if not item.evidence:
                gaps.append(f"{item.id}: cevaplanabilir soruda gold kanıt yok")
            if not item.reference_answer:
                gaps.append(f"{item.id}: referans cevap yok")
    return gaps


def set_gaps(gold: GoldSet, manifest: CorpusManifest) -> list[str]:
    """Baseline kabulü için set düzeyindeki eksikler."""
    gaps: list[str] = []
    reviewed = sum(1 for i in gold.items if i.kind is ItemKind.ANSWERABLE and i.reviewed)
    if reviewed < MIN_REVIEWED_ANSWERABLE:
        gaps.append(f"Eğitmen incelemeli cevaplanabilir soru {reviewed}/{MIN_REVIEWED_ANSWERABLE}")
    oos = sum(1 for i in gold.items if i.kind is ItemKind.OUT_OF_SCOPE)
    if oos < MIN_OUT_OF_SCOPE:
        gaps.append(f"Kapsam dışı soru {oos}/{MIN_OUT_OF_SCOPE}")
    if not any(i.split is Split.HELDOUT for i in gold.items):
        gaps.append("Held-out soru yok: ölçüm yapılamaz")
    if manifest.approved_by is None:
        gaps.append("Envanter eğitmen tarafından onaylanmamış (approved_by boş)")
    if not manifest.approved_hashes():
        gaps.append("Envanterde onaylı doküman yok")
    return gaps


def find_problems(gold: GoldSet, manifest: CorpusManifest) -> list[str]:
    """Şemanın tek başına yakalayamadığı tutarsızlıklar ve baseline eksikleri."""
    return structural_errors(gold, manifest) + item_gaps(gold) + set_gaps(gold, manifest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m harness.validate")
    parser.add_argument("gold", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--strict", action="store_true", help="eksik varsa çıkış kodu 2")
    args = parser.parse_args(argv)
    # Windows konsolu (cp1254) Türkçe karakterleri bozmasın.
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        gold = load_gold_set(args.gold)
        manifest = load_manifest(args.manifest or args.gold.parent / gold.manifest)
    except (ValidationError, OSError) as exc:
        print(f"Geçersiz: {exc}", file=sys.stderr)
        return 1
    problems = find_problems(gold, manifest)
    counts = Counter((i.split.value, i.kind.value) for i in gold.items)
    print(f"{gold.course_code}: {len(gold.items)} soru, {len(manifest.documents)} doküman")
    for (split, kind), count in sorted(counts.items()):
        print(f"  {split:<12} {kind:<13} {count}")
    for problem in problems:
        print(f"  eksik: {problem}")
    return 2 if problems and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
