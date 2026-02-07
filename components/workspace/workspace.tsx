"use client";

import { useState, useCallback } from "react";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { IntentPane } from "./intent-pane";
import { EvidencePane } from "./evidence-pane";
import { ResultsPane } from "./results-pane";
import { RunControls } from "./run-controls";

interface RunResponse {
  status: "ok" | "needs_roi";
  plan?: Record<string, unknown>;
  result?: Record<string, unknown>;
  roi_instruction?: string;
  message?: string;
}

export function Workspace() {
  const [videoId, setVideoId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [plan, setPlan] = useState<Record<string, unknown> | null>(null);
  const [runStatus, setRunStatus] = useState<"idle" | "running" | "done">("idle");
  const [runResponse, setRunResponse] = useState<RunResponse | null>(null);
  const [needsROIOpen, setNeedsROIOpen] = useState(false);
  const [needsROIData, setNeedsROIData] = useState<{
    roi_instruction: string;
    plan: Record<string, unknown>;
  } | null>(null);

  const handleRun = useCallback(async () => {
    if (!videoId) return;
    setRunStatus("running");
    setRunResponse(null);

    try {
      const res = await fetch(
        `http://localhost:8000/api/video/${videoId}/analyze`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: query.trim() || undefined }),
        }
      );
      const data = (await res.json()) as RunResponse;
      console.log("Analysis results:", data);

      if (!res.ok) {
        throw new Error(
          (data as { detail?: string }).detail ?? `Request failed: ${res.status}`
        );
      }

      setRunResponse(data);
      setPlan(data.plan ?? null);

      if (data.status === "needs_roi" && data.roi_instruction) {
        setNeedsROIData({
          roi_instruction: data.roi_instruction,
          plan: data.plan ?? {},
        });
        setNeedsROIOpen(true);
      }
    } catch (err) {
      console.error("Run failed", err);
      setRunResponse({
        status: "ok",
        message: err instanceof Error ? err.message : "Run failed",
      });
    } finally {
      setRunStatus("done");
    }
  }, [videoId, query]);

  const handleDrawROIClick = useCallback(() => {
    setNeedsROIOpen(false);
    setNeedsROIData(null);
    window.dispatchEvent(new CustomEvent("open-draw-roi"));
  }, []);

  return (
    <div className="flex h-screen flex-col">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-border bg-card px-4 py-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary">
            <span className="text-xs font-bold text-primary-foreground">
              A
            </span>
          </div>
          <span className="text-sm font-semibold text-foreground">
            Analytics Mate
          </span>
        </div>
        <span className="text-[11px] text-muted-foreground font-mono">
          v0.1.0
        </span>
      </header>

      {/* Three-pane workspace */}
      <div className="flex-1 overflow-hidden">
        <ResizablePanelGroup direction="horizontal">
          {/* Left — Intent */}
          <ResizablePanel defaultSize={22} minSize={16} maxSize={35}>
            <IntentPane
              videoId={videoId}
              onVideoSelect={setVideoId}
              query={query}
              onQueryChange={setQuery}
              plan={plan}
            />
          </ResizablePanel>

          <ResizableHandle />

          {/* Center — Evidence */}
          <ResizablePanel defaultSize={50} minSize={30}>
            <EvidencePane
              videoId={videoId}
              onVideoIdChange={setVideoId}
              runResult={runResponse?.status === "ok" ? runResponse.result : undefined}
            />
          </ResizablePanel>

          <ResizableHandle />

          {/* Right — Results */}
          <ResizablePanel defaultSize={28} minSize={18} maxSize={40}>
            <ResultsPane
              result={
                runResponse?.status === "ok" ? runResponse.result : undefined
              }
            />
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {/* Bottom run controls */}
      <RunControls
        videoId={videoId}
        onRun={handleRun}
        isRunning={runStatus === "running"}
        runComplete={runStatus === "done"}
      />

      {/* needs_roi popup — points user to Draw ROI */}
      <AlertDialog open={needsROIOpen} onOpenChange={setNeedsROIOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Region of interest required</AlertDialogTitle>
            <AlertDialogDescription>
              {needsROIData?.roi_instruction ??
                "This analysis needs a region of interest. Draw one on the video, then run again."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction onClick={handleDrawROIClick}>
              Draw ROI
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
