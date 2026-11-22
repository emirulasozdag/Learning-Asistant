import { FileText, ServerOff } from "lucide-react";

import type { SyllabusBlock } from "../../api/types";
import { useCourseOutlet } from "../../features/courses/courseOutlet";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";
import { Table, TD, TH, THead, TR } from "../../ui/Table";

/** Dersin izlencesi (OCW "Syllabus"): ön koşullar, kaynaklar, notlandırma… */
export default function SyllabusPage() {
  const { outline, outlineFailed, reloadOutline } = useCourseOutlet();

  return (
    <div>
      <PageTitle title="İzlence" description="Dersin işleyişi, ön koşulları, kaynakları ve notlandırması." />
      {outlineFailed ? (
        <EmptyState
          icon={ServerOff}
          tone="danger"
          title="İzlence yüklenemedi"
          description="Ders bilgisine şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
          action={<Button onClick={reloadOutline}>Tekrar dene</Button>}
        />
      ) : outline === null ? (
        <SkeletonRows rows={4} />
      ) : !outline.syllabus?.length ? (
        <EmptyState
          icon={FileText}
          title="Bu derse henüz izlence eklenmedi"
          description="Eğitmen izlenceyi eklediğinde ön koşullar, kaynaklar ve notlandırma burada görünür."
        />
      ) : (
        <article className="flex max-w-[70ch] flex-col gap-4 font-serif text-md leading-relaxed text-ink">
          {outline.syllabus.map((block, index) => (
            <Block key={index} block={block} />
          ))}
        </article>
      )}
    </div>
  );
}

function Block({ block }: { block: SyllabusBlock }) {
  switch (block.type) {
    case "heading":
      return <h2 className="mt-6 font-sans text-xl leading-tight font-bold tracking-tight text-ink first:mt-0">{block.text}</h2>;
    case "paragraph":
      return <p>{block.text}</p>;
    case "list":
      return (
        <ul className="flex list-disc flex-col gap-2 pl-6 marker:text-faint">
          {block.items?.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      );
    case "table": {
      const [header, ...rows] = block.rows ?? [];
      if (!header) return null;
      return (
        <div className="max-w-lg font-sans text-base">
          <Table label="İzlence tablosu">
            <THead>
              <tr>
                {header.map((cell, index) => (
                  <TH key={index}>{cell}</TH>
                ))}
              </tr>
            </THead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <TR key={rowIndex}>
                  {row.map((cell, index) => (
                    <TD key={index} className={index > 0 ? "tabular-nums" : "font-medium text-ink"}>
                      {cell}
                    </TD>
                  ))}
                </TR>
              ))}
            </tbody>
          </Table>
        </div>
      );
    }
  }
}
