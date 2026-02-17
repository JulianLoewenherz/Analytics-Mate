"use client";

import { useState } from "react";
import { Play, Loader2 } from "lucide-react";
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
