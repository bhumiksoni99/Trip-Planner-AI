import type { PlanDay } from "@/lib/api";
import Markdown from "./Markdown";

type DayPlanProps = {
  days: PlanDay[];
  onLinkClick?: (href: string, label: string) => void;
};

export default function DayPlan({ days, onLinkClick }: DayPlanProps) {
  if (!days.length) return null;

  return (
    <section className="my-6 border border-line bg-surface">
      <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <h3 className="text-sm font-semibold text-ink">Day by day</h3>
        <p className="text-xs text-faint print:hidden">Ask below to move or lighten a day</p>
      </header>

      {days.map((day, index) => (
        <div
          key={`${day.label}-${index}`}
          className="grid break-inside-avoid border-b border-line last:border-b-0 sm:grid-cols-[152px_minmax(0,1fr)]"
        >
          <div className="px-5 pt-4.5 pb-1 sm:border-r sm:border-line sm:pb-4.5">
            <p className="text-[11px] font-semibold tracking-[0.1em] text-faint uppercase">{day.label}</p>
            {day.heading && (
              <p className="mt-1.5 font-display text-[22px] leading-[1.1] text-balance text-ink">{day.heading}</p>
            )}
          </div>

          <div className="flex flex-col gap-2 px-5 py-4.5">
            {day.items.map((item, itemIndex) => (
              <div key={itemIndex} className="grid gap-3.5 sm:grid-cols-[56px_minmax(0,1fr)]">
                <p className="text-xs text-faint">{item.time}</p>
                {/* The plan keeps its Google links inside the item text */}
                <Markdown content={item.text} onLinkClick={onLinkClick} className="day-item" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
