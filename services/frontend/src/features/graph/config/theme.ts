/**
 * Resolves clinical entity colors from CSS variables at runtime.
 * Updates reactively so the graph recolors when the theme changes.
 */

import type { GraphNodeType } from "@/types/api";

export interface EntityColor {
  fill: string;
  stroke: string;
  label: string;
}

/** Read a CSS variable from the document root and format as HSL string. */
function readVar(name: string): string {
  if (typeof window === "undefined") return "#888888";
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return raw ? `hsl(${raw})` : "#888888";
}

function readVarAlpha(name: string, alpha: number): string {
  if (typeof window === "undefined") return "#888888";
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return raw ? `hsl(${raw} / ${alpha})` : "#888888";
}

export function getEntityColors(): Record<GraphNodeType, EntityColor> {
  return {
    Disease: {
      fill: readVarAlpha("--disease", 0.22),
      stroke: readVar("--disease"),
      label: readVar("--disease"),
    },
    Symptom: {
      fill: readVarAlpha("--symptom", 0.18),
      stroke: readVar("--symptom"),
      label: readVar("--symptom"),
    },
    Gene: {
      fill: readVarAlpha("--gene", 0.18),
      stroke: readVar("--gene"),
      label: readVar("--gene"),
    },
    Drug: {
      fill: readVarAlpha("--drug", 0.2),
      stroke: readVar("--drug"),
      label: readVar("--drug"),
    },
    Phenotype: {
      fill: readVarAlpha("--phenotype", 0.2),
      stroke: readVar("--phenotype"),
      label: readVar("--phenotype"),
    },
    Anatomy: {
      fill: readVarAlpha("--anatomy", 0.2),
      stroke: readVar("--anatomy"),
      label: readVar("--anatomy"),
    },
  };
}

export function getBackgroundColor(): string {
  return readVar("--background");
}

export function getForegroundColor(): string {
  return readVar("--foreground");
}

export function getMutedColor(): string {
  return readVar("--muted-foreground");
}

export function getPrimaryColor(): string {
  return readVar("--primary");
}

export function getBorderColor(): string {
  return readVar("--border");
}
