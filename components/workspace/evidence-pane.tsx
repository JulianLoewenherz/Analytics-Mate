"use client";

import { useState } from "react";
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { Separator } from "@/components/ui/separator";

export function EvidencePane() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState([0]);
  const [hasVideo, setHasVideo] = useState(false);
  const [videoMetadata, setVideoMetadata] = useState<{
    fps: number;
    frameCount: number;
    duration: number;
  } | null>(null);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="text-sm font-semibold text-foreground">Evidence</h2>
        <Badge
          variant="outline"
          className="text-[10px] text-muted-foreground border-border"
        >
          {hasVideo ? "Video Loaded" : "No Video"}
        </Badge>
      </div>

      <Separator />

      {/* Video area */}
      <div className="relative flex-1 m-3 rounded-lg border border-border bg-card overflow-hidden">
        {hasVideo ? (
          <>
            {/* Video player - will be wired up to backend */}
            <div className="absolute inset-0 bg-black flex items-center justify-center">
              <video
                className="w-full h-full object-contain"
                controls={false}
                aria-label="Uploaded video"
              >
                {/* Video source will be set via JavaScript after upload */}
              </video>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-xs text-muted-foreground/40 font-mono">
                  VIDEO PLAYER
                </span>
              </div>
            </div>

            {/* Video metadata overlay */}
            {videoMetadata && (
              <div className="absolute left-3 top-3 flex items-center gap-2">
                <Badge className="bg-card/80 text-foreground border-none text-[10px] font-mono backdrop-blur-sm">
                  {videoMetadata.fps} fps • {videoMetadata.frameCount} frames • {Math.round(videoMetadata.duration)}s
                </Badge>
              </div>
            )}
          </>
        ) : (
          /* Upload state */
          <div className="flex h-full flex-col items-center justify-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-full border-2 border-dashed border-border">
              <Upload className="h-5 w-5 text-muted-foreground" />
            </div>
            <div className="text-center">
              <p className="text-sm text-foreground font-medium">
                Upload a video
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Drag and drop or click to browse
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="mt-1 bg-transparent"
              onClick={() => {
                // TODO: Wire up to file input and backend upload
                console.log("Upload clicked - wire to backend");
              }}
            >
              Choose file
            </Button>
          </div>
        )}
      </div>

      {/* Transport controls */}
      {hasVideo && (
        <div className="px-4 pb-3 flex flex-col gap-2">
          {/* Frame scrubber */}
          <div className="flex items-center gap-3">
            <span className="text-[11px] font-mono text-muted-foreground w-10 text-right">
              {formatTime(currentTime[0])}
            </span>
            <Slider
              value={currentTime}
              onValueChange={setCurrentTime}
              min={0}
              max={videoMetadata?.duration || 120}
              step={1}
              className="flex-1"
              aria-label="Video timeline"
              disabled={!videoMetadata}
            />
            <span className="text-[11px] font-mono text-muted-foreground w-10">
              {formatTime(videoMetadata?.duration || 0)}
            </span>
          </div>

          {/* Playback buttons */}
          <div className="flex items-center justify-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              aria-label="Skip back"
              disabled={!videoMetadata}
            >
              <SkipBack className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9"
              onClick={() => setIsPlaying(!isPlaying)}
              aria-label={isPlaying ? "Pause" : "Play"}
              disabled={!videoMetadata}
            >
              {isPlaying ? (
                <Pause className="h-5 w-5" />
              ) : (
                <Play className="h-5 w-5" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              aria-label="Skip forward"
              disabled={!videoMetadata}
            >
              <SkipForward className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
