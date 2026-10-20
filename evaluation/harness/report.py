"""Koşu kaydından okunabilir özet: metrikler paydalarıyla, hesaplanamayanlar boşluk olarak."""

from harness.schemas import MetricValue, RunRecord


def fmt(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.4g}"


def header_lines(record: RunRecord) -> list[str]:
    c = record.config
    return [
        f"- Koşul: `{c.condition}` · split: `{c.split.value if c.split else 'all'}`",
        f"- Commit: `{c.git_commit or '?'}`" + (" (çalışma ağacı kirli)" if c.git_dirty else ""),
        f"- LLM: {c.llm_provider} `{c.llm_model or 'kapalı'}`"
        + (f" @ {c.llm_base_url}" if c.llm_enabled else ""),
        f"- Embedding: {c.embedding_provider} `{c.embedding_model}`",
        "- Retrieval: " + ", ".join(f"{k}={v}" for k, v in c.retrieval.items()),
        f"- Prompt SHA-256: `{c.prompt_sha256[:16]}…` · gold set: `{c.gold_set_sha256[:16]}…`"
        f" · envanter: `{c.manifest_sha256[:16]}…`",
        f"- Soru sayısı: {len(record.items)}",
    ]


def metric_table(metrics: dict[str, MetricValue]) -> list[str]:
    lines = ["| Metrik | Değer | Pay / payda | Hedef | Not |", "|---|---|---|---|---|"]
    for name, metric in metrics.items():
        ratio = (
            f"{metric.numerator}/{metric.denominator}"
            if metric.numerator is not None
            else f"n={metric.denominator}"
        )
        target, gap = metric.target or "", metric.gap or ""
        lines.append(f"| {name} | {fmt(metric.value)} | {ratio} | {target} | {gap} |")
    return lines


def render_markdown(record: RunRecord) -> str:
    lines = [f"# Değerlendirme koşusu `{record.run_id}`", "", *header_lines(record)]
    lines += ["", "## Metrikler", "", *metric_table(record.metrics)]
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
