"use client";

import { useState } from "react";
import {
  Play,
  StepForward,
  RotateCcw,
  GitCompareArrows,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";

type RunStatus = "idle" | "running" | "done";

export function RunControls() {
  const [status, setStatus] = useState<RunStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState("");

  const handleRun = () => {
    // TODO: Wire up to backend — trigger full analysis pipeline
    setStatus("running");
    setCurrentStep("Detecting objects...");
    setProgress(35);
  };

  const handleStep = () => {
    // TODO: Wire up to backend — advance one pipeline step (detect -> track -> metric)
    setStatus("running");
    setCurrentStep("Stepping: detect");
    setProgress(25);
  };

  const handleRerun = () => {
    // TODO: Wire up to backend — re-run analysis with current parameter changes
    setStatus("idle");
    setProgress(0);
    setCurrentStep("");
  };

  return (
    <div className="flex items-center gap-3 border-t border-border bg-card px-4 py-2.5">
      {/* Run button */}
      <Button
        size="sm"
        onClick={handleRun}
        disabled={status === "running"}
        className="gap-1.5"
      >
        {status === "running" ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Play className="h-3.5 w-3.5" />
        )}
        Run
      </Button>

      {/* Step through */}
      <Button
        variant="outline"
        size="sm"
        onClick={handleStep}
        disabled={status === "running"}
        className="gap-1.5 bg-transparent"
      >
        <StepForward className="h-3.5 w-3.5" />
        Step
      </Button>

      {/* Re-run */}
      <Button
        variant="outline"
        size="sm"
        onClick={handleRerun}
        className="gap-1.5 bg-transparent"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        Re-run
      </Button>

      {/* Separator */}
      <div className="h-5 w-px bg-border" />

      {/* Compare toggle */}
      <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground">
        <GitCompareArrows className="h-3.5 w-3.5" />
        Compare
      </Button>

      {/* Progress area */}
      <div className="flex flex-1 items-center gap-3 justify-end">
        {status === "running" && (
          <>
            <span className="text-[11px] text-muted-foreground font-mono truncate max-w-[200px]">
              {currentStep}
            </span>
            <Progress value={progress} className="w-32 h-1.5" />
          </>
        )}
        {status === "done" && (
          <Badge variant="secondary" className="text-[10px]">
            Completed
          </Badge>
        )}
      </div>
    </div>
  );
}
