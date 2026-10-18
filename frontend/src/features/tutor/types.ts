import type { AskResponse, RetrievalHit } from "../../api/types";

/** Sohbette bir soru ve (gelmekte olan ya da gelmiş) cevabı. */
export interface Turn {
  id: string;
  question: string;
  /** Aramanın getirdiği parçalar (cevap yazılmadan önce gelir). */
  hits?: RetrievalHit[];
  /** Model yazarken biriken metin. */
  streamText: string;
  response?: AskResponse;
  error?: string;
}

export interface SelectSourceProps {
  selectedSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
}
