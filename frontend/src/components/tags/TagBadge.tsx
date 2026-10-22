import { X } from "lucide-react";
import clsx from "clsx";
import { tagClass } from "../../types";

interface TagBadgeProps {
  tag: string;
  onRemove?: () => void;
  onClick?: () => void;
  title?: string;
}

export default function TagBadge({ tag, onRemove, onClick, title }: TagBadgeProps) {
  return (
    <span title={title} className={clsx("chip", tagClass(tag), onClick && "cursor-pointer hover:opacity-80")} onClick={onClick}>
      {tag}
      {onRemove && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="hover:opacity-70 ml-0.5"
          aria-label={`Remove tag ${tag}`}
        >
          <X size={10} />
        </button>
      )}
    </span>
  );
}
