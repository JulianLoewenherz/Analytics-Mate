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

interface RunControlsProps {
  videoId: string | null;
  onRun: () => void;
  isRunning: boolean;
  runComplete?: boolean;
}

export function RunControls({ videoId, onRun, isRunning, runComplete }: RunControlsProps) {
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState("");

  const handleRun = () => {
    setCurrentStep("Running analysis...");
    setProgress(35);
    onRun();
  };

  const handleStep = () => {
    // TODO: Wire up to backend — advance one pipeline step (detect -> track -> metric)
    setCurrentStep("Stepping: detect");
    setProgress(25);
  };

  const handleRerun = () => {
    setProgress(0);
    setCurrentStep("");
  };

  return (
    <div className="flex items-center gap-3 border-t border-border bg-card px-4 py-2.5">
      {/* Run button */}
      <Button
        size="sm"
        onClick={handleRun}
        disabled={!videoId || isRunning}
        className="gap-1.5"
      >
        {isRunning ? (
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
        disabled={isRunning}
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
        {isRunning && (
          <>
            <span className="text-[11px] text-muted-foreground font-mono truncate max-w-[200px]">
              {currentStep}
            </span>
            <Progress value={progress} className="w-32 h-1.5" />
          </>
        )}
        {runComplete && (
          <Badge variant="secondary" className="text-[10px]">
            Completed
          </Badge>
        )}
      </div>
    </div>
  );
}
