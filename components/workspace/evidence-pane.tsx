"use client";

import { useState, useRef } from "react";
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
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [videoId, setVideoId] = useState<string | null>(null);
  
  // Reference to hidden file input
  const fileInputRef = useRef<HTMLInputElement>(null);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

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
    
    setSelectedFile(file);
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
      
      // Save the video_id for later use
      const videoId = data.video_id;
      setVideoId(videoId);
      
      // Fetch real metadata from backend using OpenCV
      const metadataResponse = await fetch(`http://localhost:8000/api/video/${videoId}/metadata`);
      
      if (!metadataResponse.ok) {
        throw new Error('Failed to fetch metadata');
      }
      
      const metadata = await metadataResponse.json();
      console.log('📊 Metadata extracted:', metadata);
      
      // Update UI with real metadata
      setVideoMetadata({
        fps: metadata.fps,
        frameCount: metadata.frame_count,
        duration: metadata.duration
      });
      
      setUploadStatus("success");
      setHasVideo(true);
      
    } catch (error) {
      console.error('❌ Upload failed:', error);
      setUploadStatus("error");
      alert('Upload failed. Make sure the backend is running at http://localhost:8000');
    }
  };

  // Trigger file input click
  const handleUploadClick = () => {
    fileInputRef.current?.click();
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
            {/* Video player - loads video from backend */}
            <div className="absolute inset-0 bg-black flex items-center justify-center">
              {videoId ? (
                <video
                  src={`http://localhost:8000/api/video/${videoId}`}
                  className="w-full h-full object-contain"
                  controls={true}
                  aria-label="Uploaded video"
                />
              ) : (
                <span className="text-xs text-muted-foreground/40 font-mono">
                  LOADING VIDEO...
                </span>
              )}
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
