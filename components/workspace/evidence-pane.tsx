"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Upload, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ROICanvas, type Point } from "./roi-canvas";

interface EvidencePaneProps {
  videoId: string | null;
  onVideoIdChange: (videoId: string | null) => void;
  runResult?: Record<string, unknown> | null;
}

const BACKEND_URL = "http://localhost:8000";

export function EvidencePane({ videoId, onVideoIdChange, runResult }: EvidencePaneProps) {
  const [hasVideo, setHasVideo] = useState(false);
  const [videoMetadata, setVideoMetadata] = useState<{
    fps: number;
    frameCount: number;
    duration: number;
  } | null>(null);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");

  // ROI state (persisted via backend)
  const [showROICanvas, setShowROICanvas] = useState(false);
  const [savedROI, setSavedROI] = useState<Point[] | null>(null);
  const [roiFrameImage, setRoiFrameImage] = useState<string | null>(null);
  const [videoDimensions, setVideoDimensions] = useState<{ w: number; h: number } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const annotatedVideoRef = useRef<HTMLVideoElement>(null);

  const annotatedVideoUrl = runResult?.annotated_video_url as string | undefined;

  // Handle file selection
  const handleFileSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    
    if (!file) return;
    
    // Validate it's a video file
    if (!file.type.startsWith('video/')) {
      alert('Please select a valid video file');
      return;
    }
    
    console.log('📹 Video file selected:', {
      name: file.name,
      size: `${(file.size / 1024 / 1024).toFixed(2)} MB`,
      type: file.type
    });
    
    setUploadStatus("uploading");
    
    try {
      // Create FormData to send file to backend
      const formData = new FormData();
      formData.append('file', file);
      
      // Upload file to backend
      const response = await fetch('http://localhost:8000/api/upload', {
        method: 'POST',
        body: formData,
      });
      
      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }
      
      // Get video_id from backend response
      const data = await response.json();
      console.log('✅ Upload successful!', data);
      
      // Save the video_id - metadata will be fetched by useEffect
      const newVideoId = data.video_id;
      onVideoIdChange(newVideoId);
      setUploadStatus("success");
      
    } catch (error) {
      console.error('❌ Upload failed:', error);
      setUploadStatus("error");
      alert('Upload failed. Make sure the backend is running at http://localhost:8000');
    }
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  // Step 1: Client-side frame capture — pause video, draw current frame to canvas, get data URL
  const handleDrawROIClick = useCallback(() => {
    const video = videoRef.current;
    if (!video || !videoId) return;
    video.pause();
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h) return;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0);
    const dataUrl = canvas.toDataURL("image/jpeg");
    setVideoDimensions({ w, h });
    setRoiFrameImage(dataUrl);
    setShowROICanvas(true);
  }, [videoId]);

  const handleROISave = useCallback(
    async (polygon: Point[]) => {
      if (!videoId) return;
      try {
        const res = await fetch(`http://localhost:8000/api/video/${videoId}/roi`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ polygon }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail ?? res.statusText);
        }
        setSavedROI(polygon);
        setShowROICanvas(false);
        setRoiFrameImage(null);
      } catch (e) {
        console.error("Failed to save ROI", e);
        alert(`Failed to save ROI: ${e instanceof Error ? e.message : String(e)}`);
      }
    },
    [videoId]
  );

  const handleROICancel = useCallback(() => {
    setShowROICanvas(false);
    setRoiFrameImage(null);
  }, []);

  // Fetch metadata when videoId changes (from upload or Load video dropdown)
  useEffect(() => {
    if (!videoId) {
      setHasVideo(false);
      setVideoMetadata(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/video/${videoId}/metadata`);
        if (cancelled) return;
        if (res.ok) {
          const metadata = await res.json();
          setVideoMetadata({
            fps: metadata.fps,
            frameCount: metadata.frame_count,
            duration: metadata.duration,
          });
          setHasVideo(true);
        }
      } catch (e) {
        if (!cancelled) console.error("Failed to fetch metadata", e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [videoId]);

  // Listen for open-draw-roi event (e.g. from needs_roi popup "Draw ROI" button)
  useEffect(() => {
    const handler = () => {
      handleDrawROIClick();
    };
    window.addEventListener("open-draw-roi", handler);
    return () => window.removeEventListener("open-draw-roi", handler);
  }, [handleDrawROIClick]);

  // Load saved ROI when video is set (e.g. after upload or page load with same video)
  useEffect(() => {
    if (!videoId) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`http://localhost:8000/api/video/${videoId}/roi`);
        if (cancelled) return;
        if (res.ok) {
          const data = await res.json();
          if (data.polygon && Array.isArray(data.polygon) && data.polygon.length >= 3) {
            setSavedROI(data.polygon as Point[]);
          } else {
            setSavedROI(null);
          }
        } else {
          // 404 or error: this video has no saved ROI
          setSavedROI(null);
        }
      } catch {
        if (!cancelled) console.error("Failed to load ROI");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [videoId]);

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

      {/* Tabs + Video area */}
      <div className="relative flex flex-1 flex-col m-3 rounded-lg border border-border bg-card overflow-hidden">
        {hasVideo ? (
          <>
            {/* Tabs: Video (ROI only) | Visualized (annotated) */}
            <Tabs defaultValue="video" className="flex flex-1 flex-col min-h-0">
              <div className="flex items-center justify-between px-3 pt-2">
                <TabsList className="h-8">
                  <TabsTrigger value="video" className="text-xs px-2.5">
                    Video
                  </TabsTrigger>
                  <TabsTrigger
                    value="visualized"
                    className="text-xs px-2.5"
                    disabled={!annotatedVideoUrl}
                  >
                    Visualized
                  </TabsTrigger>
                </TabsList>
              </div>

              {/* Video tab — normal video with ROI overlay */}
              <TabsContent value="video" className="flex-1 m-0 min-h-0 data-[state=inactive]:hidden">
                <div className="relative w-full h-full min-h-[200px] bg-black flex items-center justify-center">
                  {videoId ? (
                    <>
                      <video
                        ref={videoRef}
                        crossOrigin="anonymous"
                        src={`${BACKEND_URL}/api/video/${videoId}`}
                        className="w-full h-full object-contain"
                        controls={true}
                        aria-label="Uploaded video"
                        onLoadedMetadata={() => {
                          const v = videoRef.current;
                          if (v?.videoWidth && v?.videoHeight) {
                            setVideoDimensions({ w: v.videoWidth, h: v.videoHeight });
                          }
                        }}
                      />
                      {savedROI && savedROI.length >= 3 && !showROICanvas && videoDimensions && (
                        <svg
                          className="absolute inset-0 w-full h-full pointer-events-none"
                          viewBox={`0 0 ${videoDimensions.w} ${videoDimensions.h}`}
                          preserveAspectRatio="xMidYMid meet"
                        >
                          <polygon
                            points={savedROI.map((p) => `${p.x},${p.y}`).join(" ")}
                            fill="rgba(34, 197, 94, 0.35)"
                            stroke="rgb(34, 197, 94)"
                            strokeWidth={2}
                          />
                        </svg>
                      )}
                    </>
                  ) : (
                    <span className="text-xs text-muted-foreground/40 font-mono">
                      LOADING VIDEO...
                    </span>
                  )}
                </div>
              </TabsContent>

              {/* Visualized tab — annotated video with bboxes, ROI, color-coding */}
              <TabsContent value="visualized" className="flex-1 m-0 min-h-0 data-[state=inactive]:hidden">
                <div className="relative w-full h-full min-h-[200px] bg-black flex items-center justify-center">
                  {annotatedVideoUrl ? (
                    <video
                      ref={annotatedVideoRef}
                      crossOrigin="anonymous"
                      src={`${BACKEND_URL}${annotatedVideoUrl}`}
                      className="w-full h-full object-contain"
                      controls={true}
                      aria-label="Annotated video with bounding boxes"
                    />
                  ) : (
                    <span className="text-xs text-muted-foreground/60 font-mono text-center px-4">
                      Run analysis to see the visualized version
                    </span>
                  )}
                </div>
              </TabsContent>
            </Tabs>

            {/* Video metadata overlay */}
            {videoMetadata && !showROICanvas && (
              <div className="absolute left-6 top-14 flex items-center gap-2 pointer-events-none">
                <Badge className="bg-card/80 text-foreground border-none text-[10px] font-mono backdrop-blur-sm">
                  {videoMetadata.fps} fps • {videoMetadata.frameCount} frames • {Math.round(videoMetadata.duration)}s
                </Badge>
              </div>
            )}
            {/* Draw ROI button — when video loaded and not in drawing mode */}
            {!showROICanvas && (
              <div className="absolute right-6 top-14">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={handleDrawROIClick}
                  className="gap-1.5"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Draw ROI
                </Button>
              </div>
            )}
            {/* Step 2 & 3: ROI drawing canvas — full-viewport overlay so image is as large as possible */}
            {showROICanvas && roiFrameImage && (
              <div className="fixed inset-0 z-50 h-full w-full bg-background flex flex-col">
                <ROICanvas
                  frameImage={roiFrameImage}
                  onSave={handleROISave}
                  onCancel={handleROICancel}
                />
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
                {uploadStatus === "uploading" ? "Uploading..." : "Click to browse"}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="mt-1 bg-transparent"
              onClick={handleUploadClick}
              disabled={uploadStatus === "uploading"}
            >
              {uploadStatus === "uploading" ? "Uploading..." : "Choose file"}
            </Button>
            
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              className="hidden"
              onChange={handleFileSelect}
            />
          </div>
        )}
      </div>
    </div>
  );
}
