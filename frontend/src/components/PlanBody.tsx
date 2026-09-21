import { Fragment } from "react";
import type { BriefTerm, PlanCosts, PlanDay, PlanHeader, PlanHotel } from "@/lib/api";
import CostSummary from "./CostSummary";
import DayPlan from "./DayPlan";
import HotelList from "./HotelList";
import Markdown from "./Markdown";
import PlanBrief from "./PlanBrief";
import TripHeader from "./TripHeader";

// final_response_agent leaves these lines where the cards belong, in its Hotels and Itinerary sections
const MARKERS = ["[[HOTELS]]", "[[ITINERARY]]", "[[COSTS]]"] as const;
const SPLIT = /(\[\[HOTELS\]\]|\[\[ITINERARY\]\]|\[\[COSTS\]\])/;

type PlanBodyProps = {
  content: string;
  days?: PlanDay[];
  hotels?: PlanHotel[];
  brief?: BriefTerm[];
  costs?: PlanCosts | null;
  header?: PlanHeader | null;
  onLinkClick?: (href: string, label: string) => void;
};

/** A reply in its intended order: the brief and title card, then the write-up with its cards in place. */
export default function PlanBody({ content, days, hotels, brief, header, costs, onLinkClick }: PlanBodyProps) {
  const parts = content.split(SPLIT);
  // Anything the write-up didn't place goes after it, so a missing marker never loses a card
  const unplaced = MARKERS.filter((marker) => !parts.includes(marker));

  return (
    <>
      {brief && <PlanBrief terms={brief} />}
      {header && <TripHeader header={header} />}

      {parts.map((part, index) => {
        if (part === "[[HOTELS]]") return hotels && <HotelList key={index} hotels={hotels} onLinkClick={onLinkClick} />;
        if (part === "[[ITINERARY]]") return days && <DayPlan key={index} days={days} onLinkClick={onLinkClick} />;
        if (part === "[[COSTS]]") return costs && <CostSummary key={index} costs={costs} />;
        if (!part.trim()) return null;

        return (
          <Markdown
            key={index}
            content={part.trim()}
            onLinkClick={onLinkClick}
            className={index > 0 ? "continues" : undefined}
          />
        );
      })}

      {unplaced.map((marker) => (
        <Fragment key={marker}>
          {marker === "[[HOTELS]]" && hotels && <HotelList hotels={hotels} onLinkClick={onLinkClick} />}
          {marker === "[[ITINERARY]]" && days && <DayPlan days={days} onLinkClick={onLinkClick} />}
          {marker === "[[COSTS]]" && costs && <CostSummary costs={costs} />}
        </Fragment>
      ))}
    </>
  );
}
