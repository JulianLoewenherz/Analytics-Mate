"use client";

import React from "react";

import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

function formatAggregateLabel(key: string): string {
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

function formatAggregateValue(value: unknown): string {
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return String(value);
}

function formatTime(seconds: number): string {
  if (typeof seconds !== "number" || isNaN(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}:${s.toString().padStart(2, "0")}` : `0:${s.toString().padStart(2, "0")}`;
}

interface ResultsPaneProps {
  result?: {
    aggregates?: Record<string, unknown>;
    events?: Record<string, unknown>[];
    metadata?: Record<string, unknown>;
  } | null;
}

function DwellEventCard({ event, index }: { event: Record<string, unknown>; index: number }) {
  const trackId = event.track_id as number;
  const durationSec = event.duration_sec as number;
  const startSec = (event.start_time_sec as number) ?? 0;
  const endSec = (event.end_time_sec as number) ?? 0;

  return (
    <div
      className="flex flex-col gap-1 rounded-md border border-border bg-background p-2.5"
      key={index}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground">Track {trackId}</span>
        <span className="text-sm font-bold font-mono text-foreground">
          {typeof durationSec === "number" ? durationSec.toFixed(1) : durationSec}s
        </span>
      </div>
      <span className="text-[11px] font-mono text-muted-foreground">
        {formatTime(startSec)} → {formatTime(endSec)}
      </span>
    </div>
  );
}

function TrafficEventCard({ event, index }: { event: Record<string, unknown>; index: number }) {
  const type = (event.type as string) ?? "event";
  const trackId = event.track_id as number;
  const timeSec = (event.time_sec as number) ?? 0;
  const isEntry = type === "entry";

  return (
    <div
      className="flex flex-col gap-1 rounded-md border border-border bg-background p-2.5"
      key={index}
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground">Track {trackId}</span>
        <Badge
          variant={isEntry ? "default" : "secondary"}
          className="text-[10px]"
        >
          {isEntry ? "entered" : "exited"}
        </Badge>
      </div>
      <span className="text-[11px] font-mono text-muted-foreground">
        at {formatTime(timeSec)}
      </span>
    </div>
  );
}

function GenericEventCard({ event, index }: { event: Record<string, unknown>; index: number }) {
  const type = (event.type as string) ?? "event";
  const entries = Object.entries(event).filter(([k]) => k !== "type");

  return (
    <div
      className="flex flex-col gap-1 rounded-md border border-border bg-background p-2.5"
      key={index}
    >
      <Badge variant="secondary" className="text-[10px] w-fit">
        {type}
      </Badge>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground">
        {entries.map(([k, v]) => (
          <span key={k}>
            {k}: {String(v)}
          </span>
        ))}
      </div>
    </div>
  );
}

function EventCard({
  event,
  index,
  task,
}: {
  event: Record<string, unknown>;
  index: number;
  task?: string;
}) {
  if (task === "dwell_count") {
    return <DwellEventCard event={event} index={index} />;
  }
  if (task === "traffic_count" && (event.type === "entry" || event.type === "exit")) {
    return <TrafficEventCard event={event} index={index} />;
  }
  return <GenericEventCard event={event} index={index} />;
}

export function ResultsPane({ result }: ResultsPaneProps) {
  const aggregates = result?.aggregates ?? {};
  const aggregateEntries = Object.entries(aggregates);
  const events = (result?.events ?? []) as Record<string, unknown>[];
  const task = result?.metadata?.task as string | undefined;

  return (
    <div className="flex h-full flex-col bg-card">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="text-sm font-semibold text-foreground">Results</h2>
        <Badge
          variant="outline"
          className="text-[10px] text-muted-foreground border-border"
        >
          Metrics + Events
        </Badge>
      </div>

      <Separator />

      <ScrollArea className="flex-1">
        <div className="p-4 flex flex-col gap-4">
          {/* Headline metrics — one card per aggregate from the task */}
          <div className="flex flex-col gap-2">
            <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              Headline Metrics
            </span>
            <div className="grid grid-cols-2 gap-2">
              {aggregateEntries.length > 0 ? (
                aggregateEntries.map(([key, value]) => (
                  <div
                    key={key}
                    className="flex flex-col gap-1.5 rounded-md border border-border bg-background p-3"
                  >
                    <span className="text-[11px] text-muted-foreground">
                      {formatAggregateLabel(key)}
                    </span>
                    <span className="text-xl font-bold font-mono text-foreground">
                      {formatAggregateValue(value)}
                    </span>
                  </div>
                ))
              ) : (
                <span className="text-xs text-muted-foreground col-span-2">
                  Run analysis to see metrics.
                </span>
              )}
            </div>
          </div>

          <Separator />

          {/* Event list — layout per task type */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                Events
              </span>
              <span className="text-[11px] text-muted-foreground">
                {events.length} total
              </span>
            </div>

            <div className="flex flex-col gap-1.5">
              {events.length > 0 ? (
                events.map((event, i) => (
                  <EventCard key={i} event={event} index={i} task={task} />
                ))
              ) : (
                <span className="text-xs text-muted-foreground">
                  Run analysis to see events.
                </span>
              )}
            </div>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
