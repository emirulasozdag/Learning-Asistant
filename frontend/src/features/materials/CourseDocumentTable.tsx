import { Clock, Play, PlayCircle } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import type { DocumentOut } from "../../api/types";
import { documentExtent, materialTotals, totalsHeading } from "../../labels";
import { formatRelative, formatTime } from "../../text";
import { buttonClasses } from "../../ui/buttonStyles";
import Card from "../../ui/Card";
import FileBadge from "../../ui/FileBadge";
import { Table, TD, TH, THead, TR } from "../../ui/Table";
import { useFrames } from "../video/frames";

/** Ders dokümanları tablosu (OCW "Lecture Notes" tablosu gibi): aç, sayfa sayısı, AI Tutor'a sor / izle. */
export default function CourseDocumentTable({
  documents,
  tutorPath,
}: {
  documents: DocumentOut[];
  /** Yalnızca öğrenci: satırdan AI Tutor'a geçiş. */
  tutorPath?: string;
}) {
  return (
    <Table label="Dokümanlar">
      <THead>
        <tr>
          <TH>Doküman</TH>
          <TH className="hidden text-right sm:table-cell">{totalsHeading(materialTotals(documents))}</TH>
          <TH className="hidden md:table-cell">Eklendi</TH>
          {tutorPath && (
            <TH className="text-right">
              <span className="sr-only">İşlem</span>
            </TH>
          )}
        </tr>
      </THead>
      <tbody>
        {documents.map((document) => (
          <TR key={document.id}>
            <TD>
              <div className="flex items-center gap-3">
                <TitleLink document={document} watchPath={watchPath(document, tutorPath)} />
              </div>
            </TD>
            <TD className="hidden text-right text-ink-2 tabular-nums sm:table-cell">
              {document.material_type === "video" ? documentExtent(document) : document.page_count}
            </TD>
            <TD className="hidden whitespace-nowrap text-graphite md:table-cell">
              {formatRelative(document.created_at)}
            </TD>
            {tutorPath && (
              <TD className="text-right">
                {watchPath(document, tutorPath) ? (
                  // Video çalışma ekranında açılır; sorular durdurulan anla gider (#22, #103).
                  <Link to={watchPath(document, tutorPath)!} className="link text-sm whitespace-nowrap">
                    İzle ve sor
                  </Link>
                ) : (
                  <Link to={tutorPath} className="link text-sm whitespace-nowrap">
                    AI Tutor'a sor
                  </Link>
                )}
              </TD>
            )}
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

/**
 * Ders videoları kart ızgarası: 16:9 önizleme, başlık, süre ve "İzle ve sor". Önizleme videonun
 * ilk slayt karesidir (kare çıkarılmış videoda, var olan kare uç noktasından); yoksa lacivert
 * yer tutucu. Eklenme tarihi yalnızca eğitmene gösterilir.
 */
export function CourseVideoGrid({
  documents,
  tutorPath,
  titleLevel = 3,
}: {
  documents: DocumentOut[];
  /** Yalnızca öğrenci: çalışma ekranına / AI Tutor'a geçiş. */
  tutorPath?: string;
  /** Kart başlığının seviyesi: grup başlığı yoksa 2. */
  titleLevel?: 2 | 3;
}) {
  return (
    <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {documents.map((document) => (
        <VideoCard key={document.id} document={document} tutorPath={tutorPath} titleLevel={titleLevel} />
      ))}
    </ul>
  );
}

function VideoCard({
  document,
  tutorPath,
  titleLevel,
}: {
  document: DocumentOut;
  tutorPath: string | undefined;
  titleLevel: 2 | 3;
}) {
  const watch = watchPath(document, tutorPath);
  const Heading = titleLevel === 2 ? "h2" : "h3";
  const thumbnail = <VideoThumbnail document={document} />;
  return (
    <Card as="li" padding="none" className="flex flex-col overflow-hidden">
      {watch ? (
        // Önizleme de çalışma ekranını açar; aynı bağlantı başlıkta olduğu için ekran okuyucudan ve
        // sekme sırasından gizlidir.
        <Link to={watch} tabIndex={-1} aria-hidden className="block">
          {thumbnail}
        </Link>
      ) : (
        thumbnail
      )}
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="min-w-0">
          <Heading className="text-md leading-snug font-semibold text-pretty">
            <VideoTitleLink document={document} watchPath={watch} />
          </Heading>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-graphite">
            {document.duration_s != null && (
              <span className="inline-flex items-center gap-1 tabular-nums">
                <Clock size={14} aria-hidden />
                <span className="sr-only">Süre: </span>
                {formatTime(document.duration_s)}
              </span>
            )}
            {!tutorPath && <span>Eklendi {formatRelative(document.created_at)}</span>}
          </p>
        </div>
        {tutorPath && (
          <div className="mt-auto">
            {watch ? (
              // Video çalışma ekranında açılır; sorular durdurulan anla gider (#22, #103).
              <Link to={watch} className={buttonClasses("primary", "sm")}>
                <Play size={14} aria-hidden />
                İzle ve sor
              </Link>
            ) : (
              <Link to={tutorPath} className={buttonClasses("secondary", "sm")}>
                AI Tutor'a sor
              </Link>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}

/** Kartın 16:9 önizlemesi; görüntü süs amaçlıdır (`alt=""`), başlık zaten yanında. */
function VideoThumbnail({ document }: { document: DocumentOut }) {
  // Kare yalnızca çıkarılmış videoda istenir: diğerleri için istek gitmez.
  const frames = useFrames(document.frame_count ? document.id : null);
  const [failed, setFailed] = useState(false);
  const frame = frames?.[0];
  return (
    <div className="relative flex aspect-video w-full items-center justify-center overflow-hidden border-b border-line bg-accent-soft">
      {frame && !failed ? (
        <img
          src={frame.image_url}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
          className="h-full w-full object-cover"
        />
      ) : (
        <span aria-hidden className="flex size-12 items-center justify-center rounded-full bg-surface text-accent">
          <Play size={20} className="translate-x-px" />
        </span>
      )}
    </div>
  );
}

/** Video kartının başlığı: tablodaki başlık bağlantısıyla aynı hedefler, simgesiz. */
function VideoTitleLink({ document, watchPath }: { document: DocumentOut; watchPath: string | undefined }) {
  if (watchPath) {
    return (
      <Link to={watchPath} className="link">
        {document.title}
      </Link>
    );
  }
  if (document.media_url) {
    return (
      <a href={document.media_url} target="_blank" rel="noreferrer" className="link">
        {document.title}
      </a>
    );
  }
  return (
    <a href={document.file_url} target="_blank" rel="noreferrer" className="link">
      {document.title} (transkript)
    </a>
  );
}

/** Öğrenci için videonun çalışma ekranı; video değilse ya da oynatılamıyorsa yok. */
function watchPath(document: DocumentOut, tutorPath: string | undefined): string | undefined {
  if (!tutorPath || document.material_type !== "video" || !document.media_url) return undefined;
  return `${tutorPath.replace(/\/tutor$/, "")}/watch/${document.id}`;
}

/**
 * Başlık materyalin kendisini açar. Videoda bu altyazı dosyası (VTT) değil videodur: öğrenci
 * çalışma ekranına, eğitmen videonun adresine gider. Yalnızca transkripti olan video
 * (adres verilmemiş) transkript dosyasını açar ve böyle adlandırılır.
 */
function TitleLink({ document, watchPath }: { document: DocumentOut; watchPath: string | undefined }) {
  const video = document.material_type === "video";
  if (video && watchPath) {
    return (
      <>
        <VideoBadge />
        <Link to={watchPath} className="link text-md">
          {document.title}
        </Link>
      </>
    );
  }
  if (video && document.media_url) {
    return (
      <>
        <VideoBadge />
        <a href={document.media_url} target="_blank" rel="noreferrer" className="link text-md">
          {document.title}
        </a>
      </>
    );
  }
  return (
    <>
      <FileBadge filename={document.filename} />
      <a href={document.file_url} target="_blank" rel="noreferrer" className="link text-md">
        {document.title} ({video ? "transkript" : document.filename.split(".").pop()?.toUpperCase()})
      </a>
    </>
  );
}

function VideoBadge() {
  return (
    <span
      aria-hidden
      className="flex size-8 shrink-0 items-center justify-center rounded bg-surface text-graphite ring-1 ring-line"
    >
      <PlayCircle size={16} />
    </span>
  );
}
