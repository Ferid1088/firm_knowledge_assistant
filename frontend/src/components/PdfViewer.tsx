"use client";

import { useEffect, useRef, useState } from "react";
import type { ArtifactChunk } from "@/lib/types";

// pdfjs-dist is bundled locally (no CDN worker, per CLAUDE.md air-gap rules).
// The worker file is copied to /public/pdf.worker.min.mjs at build/dev time.
type PdfJsLib = typeof import("pdfjs-dist");

const SCALE = 1.5;

export function PdfViewer({
  docId,
  highlight,
  jumpToken,
}: {
  docId: string | null;
  highlight: ArtifactChunk | null;
  jumpToken: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Record<number, HTMLDivElement>>({});
  const [error, setError] = useState<string | null>(null);
  const [renderedPages, setRenderedPages] = useState(0);

  useEffect(() => {
    if (!docId) return;
    let cancelled = false;
    let pdfjsLib: PdfJsLib | null = null;

    async function render() {
      try {
        pdfjsLib = await import("pdfjs-dist");
        pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

        const res = await fetch(`/api/originals/${encodeURIComponent(docId as string)}`);
        if (!res.ok) throw new Error(`Failed to fetch source PDF (${res.status})`);
        const buf = await res.arrayBuffer();

        const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
        if (cancelled) return;

        const container = containerRef.current;
        if (!container) return;
        container.innerHTML = "";
        pageRefs.current = {};

        for (let p = 1; p <= pdf.numPages; p++) {
          const page = await pdf.getPage(p);
          const viewport = page.getViewport({ scale: SCALE });

          const wrap = document.createElement("div");
          wrap.style.cssText = `position:relative;margin:0 auto 12px;width:${viewport.width}px;height:${viewport.height}px;box-shadow:0 1px 6px rgba(0,0,0,.2);background:#fff`;

          const canvas = document.createElement("canvas");
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          wrap.appendChild(canvas);
          container.appendChild(wrap);
          pageRefs.current[p] = wrap;

          const ctx = canvas.getContext("2d");
          if (!ctx) continue;
          await page.render({ canvasContext: ctx, viewport, canvas }).promise;
          if (!cancelled) setRenderedPages(p);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }

    render();
    return () => {
      cancelled = true;
    };
  }, [docId]);

  // Draw / refresh highlight overlays whenever the highlighted chunk changes.
  useEffect(() => {
    // Clear previous overlays
    Object.values(pageRefs.current).forEach((wrap) => {
      wrap.querySelectorAll(".citation-box").forEach((el) => el.remove());
    });

    if (!highlight) return;

    Object.entries(highlight.address.boxes).forEach(([pageNoStr, rects]) => {
      const pageNo = Number(pageNoStr);
      const wrap = pageRefs.current[pageNo];
      if (!wrap) return;
      const W = wrap.clientWidth;
      const H = wrap.clientHeight;

      rects.forEach((r) => {
        const box = document.createElement("div");
        box.className = "citation-box";
        box.style.cssText = `position:absolute;border:2px solid #e53935;background:rgba(229,57,53,.18);pointer-events:none;border-radius:2px;left:${
          r[0] * W
        }px;top:${r[1] * H}px;width:${(r[2] - r[0]) * W}px;height:${(r[3] - r[1]) * H}px`;
        wrap.appendChild(box);
      });
    });

    // Jump to the first highlighted page
    const firstPage = Object.keys(highlight.address.boxes).map(Number).sort((a, b) => a - b)[0];
    if (firstPage && pageRefs.current[firstPage]) {
      pageRefs.current[firstPage].scrollIntoView({ behavior: "smooth", block: "start" });
    }
    // jumpToken forces a re-run even if the same chunk is clicked again;
    // renderedPages re-runs this once the highlighted page's canvas has appeared.
  }, [highlight, jumpToken, renderedPages]);

  if (!docId) {
    return (
      <div className="viewer-placeholder">
        Click a citation to open its source document here.
      </div>
    );
  }

  if (error) {
    return <div className="viewer-error">Error loading PDF: {error}</div>;
  }

  return <div ref={containerRef} style={{ padding: 12 }} />;
}
