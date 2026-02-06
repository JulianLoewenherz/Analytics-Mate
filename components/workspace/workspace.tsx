"use client";

import { useState } from "react";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { IntentPane } from "./intent-pane";
import { EvidencePane } from "./evidence-pane";
import { ResultsPane } from "./results-pane";
import { RunControls } from "./run-controls";

export function Workspace() {
  const [videoId, setVideoId] = useState<string | null>(null);

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
            <IntentPane videoId={videoId} onVideoSelect={setVideoId} />
          </ResizablePanel>

          <ResizableHandle />

          {/* Center — Evidence */}
          <ResizablePanel defaultSize={50} minSize={30}>
            <EvidencePane videoId={videoId} onVideoIdChange={setVideoId} />
          </ResizablePanel>

          <ResizableHandle />

          {/* Right — Results */}
          <ResizablePanel defaultSize={28} minSize={18} maxSize={40}>
            <ResultsPane />
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>

      {/* Bottom run controls */}
      <RunControls />
    </div>
  );
}
