"use client";

import React from "react"

import {
  Users,
  Bike,
  Dog,
  Clock,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

interface Metric {
  label: string;
  value: string;
  icon: React.ReactNode;
  change?: { value: string; direction: "up" | "down" };
}

const MOCK_METRICS: Metric[] = [
  {
    label: "People detected",
    value: "142",
    icon: <Users className="h-4 w-4" />,
    change: { value: "+12", direction: "up" },
  },
  {
    label: "Bicycles",
    value: "23",
    icon: <Bike className="h-4 w-4" />,
    change: { value: "+3", direction: "up" },
  },
  {
    label: "Dogs",
    value: "8",
    icon: <Dog className="h-4 w-4" />,
  },
  {
    label: "Avg dwell time",
    value: "34s",
    icon: <Clock className="h-4 w-4" />,
    change: { value: "-5s", direction: "down" },
  },
];

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

export function ResultsPane() {
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
          {/* Headline metrics */}
          <div className="flex flex-col gap-2">
            <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              Headline Metrics
            </span>
            <div className="grid grid-cols-2 gap-2">
              {MOCK_METRICS.map((metric) => (
                <div
                  key={metric.label}
                  className="flex flex-col gap-1.5 rounded-md border border-border bg-background p-3"
                >
                  <div className="flex items-center gap-1.5 text-muted-foreground">
                    {metric.icon}
                    <span className="text-[11px]">{metric.label}</span>
                  </div>
                  <div className="flex items-end justify-between">
                    <span className="text-xl font-bold font-mono text-foreground">
                      {metric.value}
                    </span>
                    {metric.change && (
                      <span
                        className={`flex items-center gap-0.5 text-[11px] font-medium ${
                          metric.change.direction === "up"
                            ? "text-primary"
                            : "text-muted-foreground"
                        }`}
                      >
                        {metric.change.direction === "up" ? (
                          <ArrowUpRight className="h-3 w-3" />
                        ) : (
                          <ArrowDownRight className="h-3 w-3" />
                        )}
                        {metric.change.value}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Per-signal summary */}
          <div className="rounded-md border border-border bg-background p-3 flex flex-col gap-2">
            <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
              Per Signal Average
            </span>
            <div className="flex items-center justify-between">
              <span className="text-xs text-foreground">
                Crossings per walk signal
              </span>
              <span className="text-sm font-bold font-mono text-foreground">
                10.0
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-foreground">
                Signal cycles recorded
              </span>
              <span className="text-sm font-bold font-mono text-foreground">
                2
              </span>
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
