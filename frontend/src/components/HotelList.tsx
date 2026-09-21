import type { PlanHotel } from "@/lib/api";

type HotelListProps = {
  hotels: PlanHotel[];
  onLinkClick?: (href: string, label: string) => void;
};

function kicker(hotel: PlanHotel) {
  const where = hotel.area || hotel.city;
  const nights = hotel.nights ? `${hotel.nights} ${hotel.nights === 1 ? "night" : "nights"}` : null;
  return ["Stay", where, nights].filter(Boolean).join(" · ");
}

export default function HotelList({ hotels, onLinkClick }: HotelListProps) {
  if (!hotels.length) return null;

  return (
    <div className="my-6 space-y-px bg-line">
      {hotels.map((hotel) => (
        <article key={hotel.url} className="break-inside-avoid border border-line bg-surface px-5 py-4.5">
          <p className="text-[11px] font-semibold tracking-[0.1em] text-faint uppercase">{kicker(hotel)}</p>

          <h4 className="mt-1.5 font-display text-[26px] leading-none text-ink">
            <a
              href={hotel.url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:underline"
              onClick={(event) => {
                // Let ⌘/Ctrl-click open a tab as usual; a plain click opens the in-app sheet
                if (!onLinkClick || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
                event.preventDefault();
                onLinkClick(hotel.url, hotel.name);
              }}
            >
              {hotel.name}
            </a>
          </h4>

          <p className="mt-2 max-w-[62ch] text-sm leading-[1.55] text-muted">{hotel.why}</p>
        </article>
      ))}
    </div>
  );
}
