"use client";

import { useState } from "react";
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Maximize2,
  Pentagon,
  MousePointer2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import { Separator } from "@/components/ui/separator";

// Mock bounding boxes for the UI demo
const MOCK_BOXES = [
  { id: 1, label: "Person", x: 15, y: 20, w: 8, h: 18, color: "hsl(160, 70%, 45%)" },
  { id: 2, label: "Person", x: 35, y: 25, w: 7, h: 16, color: "hsl(160, 70%, 45%)" },
  { id: 3, label: "Bicycle", x: 55, y: 40, w: 10, h: 12, color: "hsl(200, 65%, 50%)" },
  { id: 4, label: "Dog", x: 72, y: 55, w: 8, h: 8, color: "hsl(40, 80%, 55%)" },
];

// Mock ROI polygon points (percentage-based)
const MOCK_ROI_POINTS = "20,60 80,60 80,90 20,90";

export function EvidencePane() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState([45]);
  const [drawMode, setDrawMode] = useState<"select" | "roi">("select");
  const [hasVideo, setHasVideo] = useState(true);

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
        <div className="flex items-center gap-2">
          {/* Drawing tools */}
          <div className="flex items-center rounded-md border border-border bg-secondary">
            <Button
              variant={drawMode === "select" ? "default" : "ghost"}
              size="sm"
              className="h-7 rounded-r-none px-2"
              onClick={() => setDrawMode("select")}
              aria-label="Select mode"
            >
              <MousePointer2 className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant={drawMode === "roi" ? "default" : "ghost"}
              size="sm"
              className="h-7 rounded-l-none px-2"
              onClick={() => setDrawMode("roi")}
              aria-label="Draw ROI polygon"
            >
              <Pentagon className="h-3.5 w-3.5" />
            </Button>
          </div>
          <Badge
            variant="outline"
            className="text-[10px] text-muted-foreground border-border"
          >
            Video + Overlays
          </Badge>
        </div>
      </div>

      <Separator />

      {/* Video area */}
      <div className="relative flex-1 m-3 rounded-lg border border-border bg-card overflow-hidden">
        {hasVideo ? (
          <>
            {/* Video placeholder frame — dark with grid lines to simulate video */}
            <div className="absolute inset-0 bg-card">
              <div
                className="absolute inset-0 opacity-[0.03]"
                style={{
                  backgroundImage:
                    "linear-gradient(hsl(220, 6%, 30%) 1px, transparent 1px), linear-gradient(90deg, hsl(220, 6%, 30%) 1px, transparent 1px)",
                  backgroundSize: "40px 40px",
                }}
              />
              {/* Simulated video content hint */}
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-xs text-muted-foreground/40 font-mono">
                  VIDEO FEED
                </span>
              </div>
            </div>

            {/* SVG overlay for bounding boxes and ROI */}
            <svg
              className="absolute inset-0 h-full w-full"
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              aria-label="Video overlay with bounding boxes and region of interest"
            >
              {/* ROI polygon */}
              <polygon
                points={MOCK_ROI_POINTS}
                fill="hsla(160, 70%, 45%, 0.08)"
                stroke="hsl(160, 70%, 45%)"
                strokeWidth="0.4"
                strokeDasharray="1.5 0.8"
              />
              <text
                x="21"
                y="58"
                fill="hsl(160, 70%, 45%)"
                fontSize="2.5"
                fontFamily="monospace"
              >
                ROI
              </text>

              {/* Bounding boxes */}
              {MOCK_BOXES.map((box) => (
                <g key={box.id}>
                  <rect
                    x={box.x}
                    y={box.y}
                    width={box.w}
                    height={box.h}
                    fill="none"
                    stroke={box.color}
                    strokeWidth="0.3"
                  />
                  <rect
                    x={box.x}
                    y={box.y - 2.5}
                    width={box.label.length * 1.6 + 2}
                    height="2.5"
                    fill={box.color}
                    rx="0.3"
                  />
                  <text
                    x={box.x + 1}
                    y={box.y - 0.6}
                    fill="hsl(240, 6%, 7%)"
                    fontSize="1.6"
                    fontWeight="bold"
                    fontFamily="monospace"
                  >
                    {box.label}
                  </text>
                </g>
              ))}
            </svg>

            {/* Frame info overlay */}
            <div className="absolute left-3 top-3 flex items-center gap-2">
              <Badge className="bg-card/80 text-foreground border-none text-[10px] font-mono backdrop-blur-sm">
                Frame 1,342 / 3,600
              </Badge>
            </div>
            <div className="absolute right-3 top-3">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 bg-card/60 backdrop-blur-sm hover:bg-card/80"
                aria-label="Fullscreen"
              >
                <Maximize2 className="h-3.5 w-3.5" />
              </Button>
            </div>
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
            <Button variant="outline" size="sm" className="mt-1 bg-transparent">
              Choose file
            </Button>
          </div>
        )}
      </div>

      {/* Transport controls */}
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
            max={120}
            step={1}
            className="flex-1"
            aria-label="Video timeline"
          />
          <span className="text-[11px] font-mono text-muted-foreground w-10">
            2:00
          </span>
        </div>

        {/* Playback buttons */}
        <div className="flex items-center justify-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label="Skip back"
          >
            <SkipBack className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-9 w-9"
            onClick={() => setIsPlaying(!isPlaying)}
            aria-label={isPlaying ? "Pause" : "Play"}
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
          >
            <SkipForward className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
