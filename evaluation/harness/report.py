"""Koşu kaydından okunabilir özet: metrikler paydalarıyla, hesaplanamayanlar boşluk olarak."""

from harness.schemas import RunRecord


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.4g}"


def render_markdown(record: RunRecord) -> str:
    c = record.config
    lines = [
        f"# Değerlendirme koşusu `{record.run_id}`",
        "",
        f"- Koşul: `{c.condition}` · split: `{c.split.value if c.split else 'all'}`",
        f"- Commit: `{c.git_commit or '?'}`" + (" (çalışma ağacı kirli)" if c.git_dirty else ""),
        f"- LLM: {c.llm_provider} `{c.llm_model or 'kapalı'}`"
        + (f" @ {c.llm_base_url}" if c.llm_enabled else ""),
        f"- Embedding: {c.embedding_provider} `{c.embedding_model}`",
        "- Retrieval: " + ", ".join(f"{k}={v}" for k, v in c.retrieval.items()),
        f"- Prompt SHA-256: `{c.prompt_sha256[:16]}…` · gold set: `{c.gold_set_sha256[:16]}…`"
        f" · envanter: `{c.manifest_sha256[:16]}…`",
        f"- Soru sayısı: {len(record.items)}",
        "",
        "## Metrikler",
        "",
        "| Metrik | Değer | Pay / payda | Hedef | Not |",
        "|---|---|---|---|---|",
    ]
    for name, metric in record.metrics.items():
        ratio = (
            f"{metric.numerator}/{metric.denominator}"
            if metric.numerator is not None
            else f"n={metric.denominator}"
        )
        target, gap = metric.target or "", metric.gap or ""
        lines.append(f"| {name} | {_fmt(metric.value)} | {ratio} | {target} | {gap} |")
    lines += ["", "## Materyal", ""]
    for document in record.corpus.documents:
        sha = document.sha256[:12] if document.sha256 else "dosya yok"
        lines.append(
            f"- {document.title} ({document.material_type}, {document.chunk_count} parça, `{sha}`)"
        )
    if record.gaps:
        lines += ["", "## Boşluklar", ""]
        lines += [f"- {gap}" for gap in record.gaps]
    errors = [item for item in record.items if item.error]
    if errors:
        lines += ["", "## Hatalar", ""]
        lines += [f"- `{item.id}`: {item.error}" for item in errors]
    return "\n".join(lines) + "\n"
