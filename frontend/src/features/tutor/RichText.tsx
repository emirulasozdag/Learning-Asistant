import "katex/dist/katex.min.css";

import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import type { Citation } from "../../api/types";
import { CitationMark } from "./CitedText";

interface CitationProps {
  /** `[n]` işaretinin kaynağı; yoksa işaret düz metin kalır. */
  resolve: (number: number) => Citation | undefined;
  selectedSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
}

/**
 * Model metni: Markdown (kalın, liste, tablo, kod) ve LaTeX matematik ($…$, $$…$$) biçimlenir.
 * `citations` verilirse doğrulanmış `[n]` işaretleri tıklanabilir kaynak numaralarına dönüşür.
 * Kod ve formül içindeki köşeli parantezlere ("A[1]") dokunulmaz.
 * `inline`: paragraf sarmalayıcısı olmadan (seçenek metinleri gibi tek satırlık yerler için).
 */
export default function RichText({
  text,
  citations,
  inline = false,
}: {
  text: string;
  citations?: CitationProps;
  inline?: boolean;
}) {
  const components: Components = {
    ...COMPONENTS,
    ...(inline ? { p: ({ children }) => <>{children}</> } : {}),
    a: ({ href, children }) => {
      const number = href?.startsWith("#cite-") ? Number(href.slice(6)) : NaN;
      const citation = citations && !Number.isNaN(number) ? citations.resolve(number) : undefined;
      if (citation && citations) {
        return (
          <CitationMark
            number={number}
            citation={citation}
            active={citation.source_id === citations.selectedSourceId}
            onSelect={citations.onSelectSource}
          />
        );
      }
      if (!Number.isNaN(number)) return <>[{number}]</>;
      return (
        <a href={href} target="_blank" rel="noreferrer" className="text-link underline">
          {children}
        </a>
      );
    },
  };
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: "ignore", output: "htmlAndMathml" }]]}
      components={components}
    >
      {citations ? linkCitations(normalizeMath(text)) : normalizeMath(text)}
    </ReactMarkdown>
  );
}

const SEGMENTS = /(```[\s\S]*?(?:```|$)|`[^`\n]*`|\$\$[\s\S]*?\$\$|\$[^$\n]+\$)/;

/**
 * JSON üreten model ters bölüyü bazen iki kez kaçırır ("$\\Theta(\\log n)$"); LaTeX'te `\\`
 * satır sonu olduğundan formül bölünür. Formül içinde harften önce gelen `\\` komut önekine
 * (`\`) indirilir. Kod blokları ve formül dışı metin olduğu gibi kalır.
 */
function normalizeMath(text: string): string {
  if (!text.includes("\\\\")) return text;
  return text
    .split(SEGMENTS)
    .map((part, index) => (index % 2 === 1 && part.startsWith("$") ? part.replace(/\\\\(?=[A-Za-z])/g, "\\") : part))
    .join("");
}

/** `[n]` → `[n](#cite-n)`; kod blokları, satır içi kod ve formüller atlanır. */
function linkCitations(text: string): string {
  return text
    .split(SEGMENTS)
    .map((part, index) =>
      index % 2 === 1 ? part : part.replace(/(?<![\w)\]])\[(\d+)\]|(?<=\])\[(\d+)\]/g, (_, a, b) => {
        const number = a ?? b;
        return `[${number}](#cite-${number})`;
      }),
    )
    .join("");
}

const COMPONENTS: Components = {
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  h1: ({ children }) => <p className="mt-4 mb-1 font-semibold text-ink">{children}</p>,
  h2: ({ children }) => <p className="mt-4 mb-1 font-semibold text-ink">{children}</p>,
  h3: ({ children }) => <p className="mt-3 mb-1 font-semibold text-ink">{children}</p>,
  h4: ({ children }) => <p className="mt-3 mb-1 font-semibold text-ink">{children}</p>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-line-strong pl-3 text-graphite">{children}</blockquote>
  ),
  code: ({ className, children }) =>
    className ? (
      <code className={className}>{children}</code>
    ) : (
      <code className="rounded bg-subtle px-1 py-0.5 font-mono text-[0.9em]">{children}</code>
    ),
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-panel bg-canvas px-3 py-2 font-mono text-sm leading-6">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="min-w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-line bg-canvas px-2 py-1 text-left font-medium">{children}</th>,
  td: ({ children }) => <td className="border border-line px-2 py-1 align-top">{children}</td>,
};
