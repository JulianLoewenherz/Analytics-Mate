"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { Button } from "@/components/ui/button";

export type Point = { x: number; y: number };

const POINT_RADIUS = 10;
const CLOSE_THRESHOLD = 18;

type ROICanvasProps = {
  frameImage: string;
  onSave: (polygon: Point[]) => void;
  onCancel: () => void;
};

export function ROICanvas({ frameImage, onSave, onCancel }: ROICanvasProps) {
  const [points, setPoints] = useState<Point[]>([]);
  const [isComplete, setIsComplete] = useState(false);
  const [hoveredPoint, setHoveredPoint] = useState<number | null>(null);
  const [mouse, setMouse] = useState<Point | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const [imageSize, setImageSize] = useState<{ w: number; h: number } | null>(null);

  // Load image and get dimensions
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      imageRef.current = img;
      setImageSize({ w: img.naturalWidth, h: img.naturalHeight });
    };
    img.src = frameImage;
  }, [frameImage]);

  const getCanvasPoint = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>): Point | null => {
      const canvas = canvasRef.current;
      if (!canvas || !imageSize) return null;
      const rect = canvas.getBoundingClientRect();
      const scaleX = imageSize.w / rect.width;
      const scaleY = imageSize.h / rect.height;
      return {
        x: (e.clientX - rect.left) * scaleX,
        y: (e.clientY - rect.top) * scaleY,
      };
    },
    [imageSize]
  );

  const isNearStartPoint = useCallback(
    (p: Point): boolean => {
      if (points.length < 3) return false;
      const start = points[0];
      const dx = p.x - start.x;
      const dy = p.y - start.y;
      return Math.sqrt(dx * dx + dy * dy) <= CLOSE_THRESHOLD;
    },
    [points]
  );

  const handleCanvasClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const p = getCanvasPoint(e);
      if (!p || !imageSize) return;
      if (isComplete) return;

      if (points.length >= 3 && isNearStartPoint(p)) {
        setIsComplete(true);
        return;
      }
      setPoints((prev) => [...prev, p]);
    },
    [getCanvasPoint, imageSize, isComplete, isNearStartPoint, points.length]
  );

  const handleDoubleClick = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      e.preventDefault();
      if (points.length >= 2 && !isComplete) {
        setIsComplete(true);
      }
    },
    [isComplete, points.length]
  );

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const p = getCanvasPoint(e);
      if (!p) return;
      setMouse(p);

      if (isComplete) {
        const idx = points.findIndex((pt, i) => {
          const dx = p.x - pt.x;
          const dy = p.y - pt.y;
          return Math.sqrt(dx * dx + dy * dy) <= POINT_RADIUS * 2;
        });
        setHoveredPoint(idx >= 0 ? idx : null);
        return;
      }

      setHoveredPoint(null);
    },
    [getCanvasPoint, isComplete, points]
  );

  const handleMouseLeave = useCallback(() => {
    setMouse(null);
    setHoveredPoint(null);
  }, []);

  const handleClear = useCallback(() => {
    setPoints([]);
    setIsComplete(false);
    setHoveredPoint(null);
  }, []);

  const handleSave = useCallback(() => {
    if (isComplete && points.length >= 3) {
      onSave(points);
    }
  }, [isComplete, points, onSave]);

  // Draw canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    const img = imageRef.current;
    if (!canvas || !img || !imageSize) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { w, h } = imageSize;
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }

    ctx.drawImage(img, 0, 0);

    if (points.length === 0) return;

    // Draw polygon fill when complete
    if (isComplete && points.length >= 3) {
      ctx.fillStyle = "rgba(59, 130, 246, 0.25)";
      ctx.beginPath();
      ctx.moveTo(points[0].x, points[0].y);
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i].x, points[i].y);
      }
      ctx.closePath();
      ctx.fill();
    }

    // Draw lines
    ctx.strokeStyle = "rgb(59, 130, 246)";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for (let i = 1; i < points.length; i++) {
      ctx.lineTo(points[i].x, points[i].y);
    }
    if (isComplete && points.length >= 3) {
      ctx.closePath();
    } else if (points.length > 0 && mouse) {
      ctx.lineTo(mouse.x, mouse.y);
    }
    ctx.stroke();

    // Draw points
    points.forEach((pt, i) => {
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, POINT_RADIUS, 0, Math.PI * 2);
      ctx.fillStyle = hoveredPoint === i ? "rgb(96, 165, 250)" : "rgb(59, 130, 246)";
      ctx.fill();
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1;
      ctx.stroke();
    });
  }, [imageSize, points, isComplete, mouse, hoveredPoint]);

  if (!imageSize) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        Loading frame…
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-3 p-3">
      <p className="text-xs text-muted-foreground">
        Click to add points. Double-click or click near the first point to close the polygon.
      </p>
      <div className="flex-1 min-h-0 flex items-center justify-center bg-black rounded overflow-hidden">
        <canvas
          ref={canvasRef}
          width={imageSize.w}
          height={imageSize.h}
          className="max-w-full max-h-full object-contain cursor-crosshair"
          style={{ imageRendering: "crisp-edges" }}
          onClick={handleCanvasClick}
          onDoubleClick={handleDoubleClick}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        />
      </div>
      <div className="flex items-center justify-between gap-2">
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={handleClear}>
            Clear
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handleSave}
            disabled={!isComplete || points.length < 3}
          >
            Save
          </Button>
        </div>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
