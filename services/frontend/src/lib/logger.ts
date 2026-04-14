/**
 * Structured logger for the frontend.
 *
 * In development, logs to the browser console with formatting.
 * In production, silences info/debug and sends warn/error to the console.
 * Hooks can be added here for Sentry, Langfuse, etc.
 */

type LogLevel = "debug" | "info" | "warn" | "error";

interface LogContext {
  [key: string]: unknown;
}

const LEVEL_ORDER: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const minLevel: LogLevel = import.meta.env.DEV ? "debug" : "info";

const LEVEL_STYLES: Record<LogLevel, string> = {
  debug: "color: #9CA3AF; font-weight: 400",
  info: "color: #60A5FA; font-weight: 500",
  warn: "color: #F59E0B; font-weight: 600",
  error: "color: #EF4444; font-weight: 700",
};

function log(level: LogLevel, message: string, context?: LogContext): void {
  if (LEVEL_ORDER[level] < LEVEL_ORDER[minLevel]) return;

  const timestamp = new Date().toISOString();
  const style = LEVEL_STYLES[level];
  const prefix = `%c[${level}]%c ${timestamp}`;

  if (context && Object.keys(context).length > 0) {
    console[level === "debug" ? "log" : level](
      `${prefix} ${message}`,
      style,
      "color: inherit",
      context,
    );
  } else {
    console[level === "debug" ? "log" : level](
      `${prefix} ${message}`,
      style,
      "color: inherit",
    );
  }
}

export const logger = {
  debug: (message: string, context?: LogContext) => log("debug", message, context),
  info: (message: string, context?: LogContext) => log("info", message, context),
  warn: (message: string, context?: LogContext) => log("warn", message, context),
  error: (message: string, context?: LogContext) => log("error", message, context),
};
