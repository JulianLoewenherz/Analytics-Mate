"use client";

import React from "react"

import { useState } from "react";
import {
  Search,
  ChevronDown,
  ChevronRight,
  Pencil,
  Eye,
  GitBranch,
  BarChart3,
  Target,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";

const EXAMPLE_QUESTIONS = [
  "How many people are bicycling?",
  "How many dogs are in this park?",
  "How many people cross per walk signal on average?",
  "What is the average dwell time at the entrance?",
];

interface PlanStep {
  id: string;
  label: string;
  description: string;
  icon: React.ReactNode;
  status: "pending" | "active" | "done";
}

const MOCK_PLAN: PlanStep[] = [
  {
    id: "detect",
    label: "Detect objects",
    description: "Identify people, bikes, and dogs in each frame",
    icon: <Eye className="h-3.5 w-3.5" />,
    status: "done",
  },
  {
    id: "track",
    label: "Track across frames",
    description: "Assign persistent IDs and build motion trajectories",
    icon: <GitBranch className="h-3.5 w-3.5" />,
    status: "active",
  },
  {
    id: "count",
    label: "Count entries into ROI",
    description: "Tally objects entering the defined region of interest",
    icon: <Target className="h-3.5 w-3.5" />,
    status: "pending",
  },
  {
    id: "aggregate",
    label: "Aggregate by signal",
    description: "Group counts per walk signal cycle and compute averages",
    icon: <BarChart3 className="h-3.5 w-3.5" />,
    status: "pending",
  },
];

export function IntentPane() {
  const [query, setQuery] = useState("");
  const [planExpanded, setPlanExpanded] = useState(true);
  const [paramsExpanded, setParamsExpanded] = useState(true);
  const [confidenceThreshold, setConfidenceThreshold] = useState([50]);
  const [timeWindow, setTimeWindow] = useState([30]);

  const handleExampleClick = (q: string) => {
    setQuery(q);
  };

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
                onChange={(e) => setQuery(e.target.value)}
                placeholder="e.g. How many people are bicycling?"
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

          <Separator />

          {/* Analysis Plan */}
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => setPlanExpanded(!planExpanded)}
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
            >
              {planExpanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              Analysis Plan
            </button>

            {planExpanded && (
              <div className="flex flex-col gap-1">
                {MOCK_PLAN.map((step, index) => (
                  <div
                    key={step.id}
                    className="flex items-start gap-2.5 rounded-md border border-border bg-background p-2.5"
                  >
                    {/* Step number + connector */}
                    <div className="flex flex-col items-center gap-1">
                      <div
                        className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${
                          step.status === "done"
                            ? "bg-primary text-primary-foreground"
                            : step.status === "active"
                              ? "border-2 border-primary text-primary"
                              : "border border-border text-muted-foreground"
                        }`}
                      >
                        {index + 1}
                      </div>
                      {index < MOCK_PLAN.length - 1 && (
                        <div className="h-4 w-px bg-border" />
                      )}
                    </div>

                    {/* Content */}
                    <div className="flex flex-1 flex-col gap-0.5 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`text-xs font-medium ${step.status === "done" ? "text-primary" : "text-foreground"}`}
                        >
                          {step.label}
                        </span>
                        {step.icon}
                      </div>
                      <span className="text-[11px] text-muted-foreground leading-relaxed">
                        {step.description}
                      </span>
                    </div>

                    {/* Edit button */}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 shrink-0"
                      aria-label={`Edit step: ${step.label}`}
                    >
                      <Pencil className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <Separator />

          {/* Parameters */}
          <div className="flex flex-col gap-3">
            <button
              type="button"
              onClick={() => setParamsExpanded(!paramsExpanded)}
              className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
            >
              {paramsExpanded ? (
                <ChevronDown className="h-3 w-3" />
              ) : (
                <ChevronRight className="h-3 w-3" />
              )}
              Parameters
            </button>

            {paramsExpanded && (
              <div className="flex flex-col gap-4">
                {/* Confidence threshold */}
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-muted-foreground">
                      Confidence threshold
                    </label>
                    <span className="text-xs font-mono text-foreground">
                      {confidenceThreshold[0]}%
                    </span>
                  </div>
                  <Slider
                    value={confidenceThreshold}
                    onValueChange={setConfidenceThreshold}
                    min={0}
                    max={100}
                    step={5}
                    className="w-full"
                  />
                </div>

                {/* Time window */}
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-muted-foreground">
                      Time window (seconds)
                    </label>
                    <span className="text-xs font-mono text-foreground">
                      {timeWindow[0]}s
                    </span>
                  </div>
                  <Slider
                    value={timeWindow}
                    onValueChange={setTimeWindow}
                    min={5}
                    max={120}
                    step={5}
                    className="w-full"
                  />
                </div>

                {/* ROI indicator */}
                <div className="flex items-center justify-between rounded-md border border-border bg-background p-2.5">
                  <div className="flex flex-col gap-0.5">
                    <span className="text-xs text-foreground font-medium">
                      Region of Interest
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      Draw on the video to define
                    </span>
                  </div>
                  <Badge variant="secondary" className="text-[10px]">
                    Not set
                  </Badge>
                </div>
              </div>
            )}
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
