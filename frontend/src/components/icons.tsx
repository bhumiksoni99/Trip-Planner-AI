type IconProps = { className?: string };

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

export function PlusIcon({ className = "size-4" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke}>
      <path d="M10 4v12M4 10h12" />
    </svg>
  );
}

export function MenuIcon({ className = "size-5" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke}>
      <path d="M3.5 6h13M3.5 10h13M3.5 14h13" />
    </svg>
  );
}

export function SidebarIcon({ className = "size-5" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke}>
      <rect x="2.75" y="3.75" width="14.5" height="12.5" rx="2.5" />
      <path d="M7.5 3.75v12.5" />
    </svg>
  );
}

export function CloseIcon({ className = "size-5" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke}>
      <path d="m5 5 10 10M15 5 5 15" />
    </svg>
  );
}

export function ChatIcon({ className = "size-4" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke}>
      <path d="M4 15.5V6a2.5 2.5 0 0 1 2.5-2.5h7A2.5 2.5 0 0 1 16 6v5a2.5 2.5 0 0 1-2.5 2.5H7l-3 2Z" />
    </svg>
  );
}

export function TrashIcon({ className = "size-4" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke}>
      <path d="M4 6h12M8 6V4.5h4V6M6 6l.7 9.2a1.5 1.5 0 0 0 1.5 1.3h3.6a1.5 1.5 0 0 0 1.5-1.3L14 6" />
    </svg>
  );
}

export function SendIcon({ className = "size-4" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke} strokeWidth={2}>
      <path d="M10 16V4m0 0-5 5m5-5 5 5" />
    </svg>
  );
}

export function CopyIcon({ className = "size-4" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke}>
      <rect x="7" y="7" width="10" height="10" rx="2.5" />
      <path d="M13 7V5.5A2.5 2.5 0 0 0 10.5 3h-5A2.5 2.5 0 0 0 3 5.5v5A2.5 2.5 0 0 0 5.5 13H7" />
    </svg>
  );
}

export function CheckIcon({ className = "size-4" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke}>
      <path d="m4.5 10.5 3.5 3.5 7.5-8" />
    </svg>
  );
}

export function DownloadIcon({ className = "size-4" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke}>
      <path d="M10 3v10m0 0-4-4m4 4 4-4M4 16h12" />
    </svg>
  );
}

export function RetryIcon({ className = "size-4" }: IconProps) {
  return (
    <svg aria-hidden viewBox="0 0 20 20" className={className} {...stroke}>
      <path d="M15.5 9.5a5.5 5.5 0 1 1-1.6-3.9M16 3.5v3h-3" />
    </svg>
  );
}
