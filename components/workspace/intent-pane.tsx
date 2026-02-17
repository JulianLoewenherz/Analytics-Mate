"use client";

import React, { useState, useEffect } from "react";
import {
  Search,
  ChevronDown,
  ChevronRight,
  Pencil,
  Eye,
  GitBranch,
  BarChart3,
  Target,
  Video,
  FileJson,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const EXAMPLE_QUESTIONS = [
  // Whole-video — no ROI needed
  "Count all cars in the video",
  // Appearance / color filtering — no ROI needed
  "How many people have a green shirt?",
  // ROI-based dwell
  "How many people loiter at the entrance for 5+ seconds?",
  // ROI-based traffic
  "How many people cross the crosswalk?",
  "How many people enter the store?",
];

interface PlanStep {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
}

const MOCK_PLAN: PlanStep[] = [
  {
    id: "ingest",
    label: "Ingest video",
    description: "Your video is uploaded, stored, and prepared for frame-by-frame analysis.",
    icon: <Video className="h-3.5 w-3.5" />,
  },
  {
    id: "detect_track",
    label: "Detect + track objects",
    description: "The system detects people and other objects in each frame and links them over time into trajectories.",
    icon: <GitBranch className="h-3.5 w-3.5" />,
  },
  {
    id: "measure",
    label: "Measure events",
    description: "High-level events are computed from those trajectories, such as entries, exits, dwell time, and crossings.",
    icon: <Target className="h-3.5 w-3.5" />,
  },
  {
    id: "aggregate",
    label: "Aggregate results",
    description: "Those events are aggregated into metrics and visual summaries that power the charts and overlays you see.",
    icon: <BarChart3 className="h-3.5 w-3.5" />,
  },
];

interface IntentPaneProps {
  videoId: string | null;
  onVideoSelect: (videoId: string | null) => void;
  query: string;
  onQueryChange: (q: string) => void;
  plan: Record<string, unknown> | null;
}

export function IntentPane({ videoId, onVideoSelect, query, onQueryChange, plan }: IntentPaneProps) {
  const [previousVideos, setPreviousVideos] = useState<{ video_id: string }[]>([]);

  const handleExampleClick = (q: string) => {
    onQueryChange(q);
  };

  // Fetch list of previously uploaded videos on mount
  useEffect(() => {
    fetch("http://localhost:8000/api/videos")
      .then((res) => res.ok ? res.json() : Promise.reject(res))
      .then((data) => setPreviousVideos(data.videos ?? []))
      .catch(() => setPreviousVideos([]));
  }, []);

  return (
    <div className="flex h-full flex-col bg-card">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="text-sm font-semibold text-foreground">Intent</h2>
        <Badge
          variant="outline"
          className="text-[10px] text-muted-foreground border-border"
        >
          Question + Plan
        </Badge>
      </div>

      <Separator />

      <ScrollArea className="flex-1">
        <div className="p-4 flex flex-col gap-4">
          {/* Load video dropdown */}
          <div className="flex flex-col gap-2">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
              <Video className="h-3.5 w-3.5" />
              Load video
            </label>
            <Select
              value={videoId ?? ""}
              onValueChange={(v) => onVideoSelect(v || null)}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Select a previously uploaded video" />
              </SelectTrigger>
              <SelectContent>
                {(() => {
                // Include current videoId if not in list (e.g. just uploaded)
                const ids = new Set(previousVideos.map((v) => v.video_id));
                const list =
                  videoId && !ids.has(videoId)
                    ? [{ video_id: videoId }, ...previousVideos]
                    : previousVideos;
                if (list.length === 0) {
                  return (
                    <SelectItem value="__empty__" disabled>
                      No videos found
                    </SelectItem>
                  );
                }
                return list.map((v) => (
                  <SelectItem key={v.video_id} value={v.video_id}>
                    {v.video_id}
                  </SelectItem>
                ));
              })()}
              </SelectContent>
            </Select>
          </div>

          <Separator />

          {/* Prompt | Plan toggle */}
          <Tabs defaultValue="prompt" className="w-full">
            <TabsList className="grid w-full grid-cols-2 h-8">
              <TabsTrigger value="prompt" className="gap-1.5 text-xs">
                <Search className="h-3.5 w-3.5" />
                Prompt
              </TabsTrigger>
              <TabsTrigger value="plan" className="gap-1.5 text-xs">
                <FileJson className="h-3.5 w-3.5" />
                Plan (JSON)
              </TabsTrigger>
            </TabsList>
            <TabsContent value="prompt" className="flex flex-col gap-2 mt-2">
              {/* Prompt box */}
              <div className="flex flex-col gap-2">
                <label
                  htmlFor="query-input"
                  className="text-xs font-medium text-muted-foreground uppercase tracking-wider"
                >
                  Ask a question
                </label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <textarea
                    id="query-input"
                    value={query}
                    onChange={(e) => onQueryChange(e.target.value)}
                    placeholder="e.g. How many people dwell in the ROI zone for 5 seconds?"
                    className="w-full resize-none rounded-md border border-input bg-background py-2.5 pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring min-h-[72px]"
                    rows={2}
                  />
                </div>
              </div>

              {/* Example questions */}
              <div className="flex flex-col gap-1.5">
                <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                  Examples
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {EXAMPLE_QUESTIONS.map((q) => (
                    <button
                      key={q}
                      type="button"
                      onClick={() => handleExampleClick(q)}
                      className="rounded-md border border-border bg-secondary px-2.5 py-1 text-xs text-secondary-foreground hover:bg-secondary/80 transition-colors text-left"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            </TabsContent>
            <TabsContent value="plan" className="mt-2">
              <div className="rounded-md border border-border bg-background p-3 min-h-[120px]">
                {plan ? (
                  <pre className="text-[11px] font-mono text-foreground overflow-auto max-h-[240px] whitespace-pre-wrap break-words">
                    {JSON.stringify(plan, null, 2)}
                  </pre>
                ) : (
                  <span className="text-xs text-muted-foreground">
                    Run analysis to see the generated plan here.
                  </span>
                )}
              </div>
            </TabsContent>
          </Tabs>

          <Separator />

          {/* How the system works */}
          <div className="flex flex-col gap-2">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                How the system works
              </span>
              <span className="text-[11px] text-muted-foreground">
                A high-level overview of the steps the system takes to turn raw video into the metrics and visuals shown in the results pane.
              </span>
            </div>

            <div className="flex flex-col gap-1">
              {MOCK_PLAN.map((step, index) => (
                <div
                  key={step.id}
                  className="flex items-start gap-2.5 rounded-md border border-border bg-background p-2.5"
                >
                  {/* Step number + connector */}
                  <div className="flex flex-col items-center gap-1">
                    <div className="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold bg-primary text-primary-foreground">
                      {index + 1}
                    </div>
                    {index < MOCK_PLAN.length - 1 && (
                      <div className="h-4 w-px bg-border" />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex flex-1 flex-col gap-0.5 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-medium text-foreground">
                        {step.label}
                      </span>
                      {step.icon}
                    </div>
                    <span className="text-[11px] text-muted-foreground leading-relaxed">
                      {step.description}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>
      </ScrollArea>
    </div>
  );
}
