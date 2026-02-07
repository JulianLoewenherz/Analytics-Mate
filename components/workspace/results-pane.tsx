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

interface ResultsPaneProps {
  result?: { aggregates?: Record<string, unknown> } | null;
}

interface Event {
  id: string;
  type: string;
  description: string;
  timestamp: string;
  frame: number;
}

const MOCK_EVENTS: Event[] = [
  {
    id: "e1",
    type: "crossing",
    description: "Person entered ROI (northbound)",
    timestamp: "0:12",
    frame: 360,
  },
  {
    id: "e2",
    type: "crossing",
    description: "Cyclist passed through ROI",
    timestamp: "0:24",
    frame: 720,
  },
  {
    id: "e3",
    type: "dwell",
    description: "Person dwelled for 45s near entrance",
    timestamp: "0:38",
    frame: 1140,
  },
  {
    id: "e4",
    type: "crossing",
    description: "Dog entered ROI with owner",
    timestamp: "0:52",
    frame: 1560,
  },
  {
    id: "e5",
    type: "signal",
    description: "Walk signal cycle completed (12 crossings)",
    timestamp: "1:05",
    frame: 1950,
  },
  {
    id: "e6",
    type: "crossing",
    description: "2 people entered ROI (southbound)",
    timestamp: "1:18",
    frame: 2340,
  },
  {
    id: "e7",
    type: "dwell",
    description: "Person dwelled for 22s at bench",
    timestamp: "1:32",
    frame: 2760,
  },
  {
    id: "e8",
    type: "signal",
    description: "Walk signal cycle completed (8 crossings)",
    timestamp: "1:45",
    frame: 3150,
  },
];

function getEventBadgeVariant(type: string) {
  switch (type) {
    case "crossing":
      return "default";
    case "dwell":
      return "secondary";
    case "signal":
      return "outline";
    default:
      return "secondary";
  }
}

export function ResultsPane({ result }: ResultsPaneProps) {
  const aggregates = result?.aggregates ?? {};
  const aggregateEntries = Object.entries(aggregates);

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

          {/* Event list */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
                Events
              </span>
              <span className="text-[11px] text-muted-foreground">
                {MOCK_EVENTS.length} total
              </span>
            </div>

            <div className="flex flex-col gap-1">
              {MOCK_EVENTS.map((event) => (
                <button
                  key={event.id}
                  type="button"
                  className="flex items-start gap-2.5 rounded-md border border-border bg-background p-2.5 text-left hover:bg-secondary/50 transition-colors group w-full"
                  aria-label={`Jump to ${event.description} at ${event.timestamp}`}
                >
                  <span className="text-[11px] font-mono text-muted-foreground w-8 pt-0.5 shrink-0">
                    {event.timestamp}
                  </span>
                  <div className="flex flex-1 flex-col gap-1 min-w-0">
                    <span className="text-xs text-foreground leading-relaxed">
                      {event.description}
                    </span>
                    <Badge
                      variant={getEventBadgeVariant(event.type)}
                      className="text-[10px] w-fit"
                    >
                      {event.type}
                    </Badge>
                  </div>
                  <span className="text-[10px] font-mono text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity pt-0.5 shrink-0">
                    Jump
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}
