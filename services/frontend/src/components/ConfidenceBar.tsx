/** Confidence bar visualization for a single diagnosis. */

interface ConfidenceBarProps {
  confidence: number;
  verified: boolean;
}

export default function ConfidenceBar({ confidence, verified }: ConfidenceBarProps) {
  const pct = Math.round(confidence * 100);
  const color =
    confidence >= 0.7
      ? "bg-green-500"
      : confidence >= 0.4
        ? "bg-yellow-500"
        : "bg-red-500";

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-700 rounded-full h-2.5 overflow-hidden">
        <div
          className={`h-full rounded-full ${color} transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-400 w-10 text-right">{pct}%</span>
      <span
        className={`text-xs px-1.5 py-0.5 rounded ${
          verified
            ? "bg-green-900/50 text-green-400"
            : "bg-orange-900/50 text-orange-400"
        }`}
      >
        {verified ? "Verified" : "Unverified"}
      </span>
    </div>
  );
}
