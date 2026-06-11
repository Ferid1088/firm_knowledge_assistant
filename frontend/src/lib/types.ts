// Mirrors src/api.py response models. Backend is the source of truth.

export type Claim = {
  text: string;
  source: number;
  quote: string;
  verified: boolean;
};

export type Box = [number, number, number, number];

export type ArtifactChunk = {
  source: number;
  chunk_id: string;
  text: string;
  quote: string;
  verified?: boolean;
  address: {
    doc_id: string;
    page: number | null;
    heading_path: string[];
    boxes: Record<string, Box[]>;
  };
};

export type ChatResponse = {
  answer: string;
  answer_lang: string;
  confidence: number;
  attempts: number;
  supporting_points: string[];
  caveats: string[];
  claims: Claim[];
  artifact_chunks: ArtifactChunk[];
};

export type IngestJobStatus = {
  job_id: string;
  status: "queued" | "running" | "done" | "error";
  doc_id: string;
  n_chunks: number | null;
  error: string | null;
};
