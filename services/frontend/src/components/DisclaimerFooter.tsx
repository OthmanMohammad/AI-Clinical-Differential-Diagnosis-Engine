/** Mandatory disclaimer footer — always visible. */

interface DisclaimerFooterProps {
  text: string;
}

export default function DisclaimerFooter({ text }: DisclaimerFooterProps) {
  return (
    <div className="border-t border-gray-800 pt-3 mt-4">
      <p className="text-xs text-gray-500 leading-relaxed">{text}</p>
    </div>
  );
}
