"use client";

import { useEffect, useRef, useState } from "react";
import type { ArtifactChunk } from "@/lib/types";
import { AlertTriangleIcon, FileSearchIcon } from "@/components/icons";

// pdfjs-dist is bundled locally (no CDN worker, per CLAUDE.md air-gap rules).
// The worker file is copied to /public/pdf.worker.min.mjs at build/dev time.
type PdfJsLib = typeof import("pdfjs-dist");

const SCALE = 1.5;
const PAGE_GAP = 12; // px between page wraps (matches margin-bottom in style)

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
  const observerRef = useRef<IntersectionObserver | null>(null);
  const [error, setError] = useState<string | null>(null);
  // layoutReady: true once ALL placeholder divs are in the DOM (scroll works).
  // renderedPages: count of fully-rendered canvases (for overlay redraw timing).
  const [layoutReady, setLayoutReady] = useState(false);
  const [renderedPages, setRenderedPages] = useState(0);

  useEffect(() => {
    if (!docId) return;
    let cancelled = false;

    async function render() {
      try {
        const pdfjsLib: PdfJsLib = await import("pdfjs-dist");
        pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

        const res = await fetch(`/api/originals/${encodeURIComponent(docId as string)}`);
        if (!res.ok) throw new Error(`Failed to fetch source PDF (${res.status})`);
        const buf = await res.arrayBuffer();

        const pdf = await pdfjsLib.getDocument({ data: buf }).promise;
        if (cancelled) return;

        const container = containerRef.current;
        if (!container) return;

        // Reset state
        container.innerHTML = "";
        pageRefs.current = {};
        if (observerRef.current) {
          observerRef.current.disconnect();
          observerRef.current = null;
        }
        setLayoutReady(false);
        setRenderedPages(0);

        // Use first-page dimensions for all placeholders (typical for legal docs).
        // Pages that differ will self-correct when their canvas renders.
        const firstPageObj = await pdf.getPage(1);
        const firstViewport = firstPageObj.getViewport({ scale: SCALE });
        const placeholderW = firstViewport.width;
        const placeholderH = firstViewport.height;

        // ── Create placeholder divs for ALL pages immediately ──────────────
        // This makes the scroll container full-height so scrollIntoView works
        // even before canvases are painted.
        for (let p = 1; p <= pdf.numPages; p++) {
          const wrap = document.createElement("div");
          wrap.style.cssText = `position:relative;margin:0 auto ${PAGE_GAP}px;width:${placeholderW}px;height:${placeholderH}px;box-shadow:0 1px 6px rgba(0,0,0,.2);background:#f5f5f5`;
          wrap.dataset.page = String(p);
          container.appendChild(wrap);
          pageRefs.current[p] = wrap;
        }

        // Placeholders are in DOM → scrolling and highlight overlay now work.
        if (!cancelled) setLayoutReady(true);

        // ── Lazy-render canvas when a placeholder scrolls into view ────────
        const renderCanvas = async (p: number) => {
          if (cancelled) return;
          const wrap = pageRefs.current[p];
          if (!wrap || wrap.querySelector("canvas")) return; // already rendered

          const page = await pdf.getPage(p);
          const viewport = page.getViewport({ scale: SCALE });

          // Correct placeholder dimensions if this page differs from first page
          wrap.style.width = `${viewport.width}px`;
          wrap.style.height = `${viewport.height}px`;

          const canvas = document.createElement("canvas");
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          wrap.appendChild(canvas);
          wrap.style.background = "#fff";

          const ctx = canvas.getContext("2d");
          if (!ctx || cancelled) return;
          await page.render({ canvasContext: ctx, viewport, canvas }).promise;
          if (!cancelled) setRenderedPages((n) => n + 1);
        };

        // 200px root margin ensures pages render slightly before they are visible.
        const observer = new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              if (entry.isIntersecting) {
                const p = Number((entry.target as HTMLElement).dataset.page);
                renderCanvas(p);
              }
            });
          },
          { root: container, rootMargin: "200px 0px", threshold: 0 }
        );

        observerRef.current = observer;
        Object.values(pageRefs.current).forEach((wrap) => observer.observe(wrap));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }

    render();
    return () => {
      cancelled = true;
      if (observerRef.current) {
        observerRef.current.disconnect();
        observerRef.current = null;
      }
    };
  }, [docId]);

  // ── Effect 1: Scroll to the cited page ────────────────────────────────────
  // Fires ONLY when the user clicks a citation (jumpToken) or when the
  // placeholder layout first becomes ready (layoutReady). Does NOT fire on
  // every canvas render so the user can scroll freely after jumping.
  useEffect(() => {
    if (!highlight) return;

    const firstPage =
      Object.keys(highlight.address.boxes).length > 0
        ? Object.keys(highlight.address.boxes).map(Number).sort((a, b) => a - b)[0]
        : highlight.address.page ?? null;

    if (!firstPage) return;

    if (pageRefs.current[firstPage]) {
      pageRefs.current[firstPage].scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (containerRef.current) {
      // Placeholders not yet in DOM (still loading) — estimate scroll position.
      const anyWrap = Object.values(pageRefs.current)[0];
      if (anyWrap) {
        const pageH = anyWrap.offsetHeight + PAGE_GAP;
        containerRef.current.scrollTop = (firstPage - 1) * pageH;
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jumpToken, layoutReady]);

  // ── Effect 2: Draw / refresh highlight overlay boxes ──────────────────────
  // Redraws on highlight change and after each canvas render (so the box
  // dimensions are correct if the canvas size differs from the placeholder).
  // Does NOT scroll — the user stays wherever they scrolled to.
  useEffect(() => {
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
  }, [highlight, renderedPages]);

  if (!docId) {
    return (
      <div className="pdf-viewer-shell pdf-viewer-shell-empty">
        <div className="pdf-viewer-topbar">
          <div>
            <span className="pdf-viewer-eyebrow">Document viewer</span>
            <h3>Source preview</h3>
          </div>
        </div>
        <div className="pdf-empty">
          <FileSearchIcon />
          <h4>Select a citation to inspect the original document.</h4>
          <p>The referenced PDF page will open here with the relevant section highlighted.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="pdf-viewer-shell pdf-viewer-shell-empty">
        <div className="pdf-viewer-topbar">
          <div>
            <span className="pdf-viewer-eyebrow">Document viewer</span>
            <h3>{docId}</h3>
          </div>
        </div>
        <div className="pdf-error">
          <AlertTriangleIcon />
          <h4>Error loading PDF</h4>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="pdf-viewer-shell">
      <div className="pdf-viewer-topbar">
        <div>
          <span className="pdf-viewer-eyebrow">Document viewer</span>
          <h3>{docId}</h3>
        </div>
        <div className="pdf-viewer-status">
          {layoutReady ? `${renderedPages} pages rendered` : "Loading…"}
        </div>
      </div>
      <div ref={containerRef} className="pdf-canvas-stage" />
    </div>
  );
}
