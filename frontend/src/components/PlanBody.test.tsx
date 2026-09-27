import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PlanCosts, PlanDay, PlanHotel } from "@/lib/api";
import PlanBody from "./PlanBody";

const days: PlanDay[] = [
  { label: "Day 1", heading: "Arrive in Tokyo", items: [{ time: "Evening", text: "Walk Shibuya" }] },
];

const hotels: PlanHotel[] = [
  { name: "Hotel Gracery", url: "https://example.com/gracery", city: "Tokyo", area: "Shinjuku", nights: 2, why: "Central" },
];

const costs: PlanCosts = {
  lines: [{ label: "Flights", amount: "Rs 40,000", note: "Return, economy" }],
  total: "Rs 1,20,000",
  ceiling: "Rs 2,00,000",
  percent: 60,
};

const card = {
  days: () => screen.queryByRole("heading", { name: "Day by day" }),
  hotels: () => screen.queryByText("Stay · Shinjuku · 2 nights"),
  costs: () => screen.queryByRole("heading", { name: "Cost summary" }),
};

describe("<PlanBody />", () => {
  it("puts each card where the write-up left its marker", () => {
    render(
      <PlanBody
        content={"## Hotels\nWhere you sleep.\n\n[[HOTELS]]\n\n[[ITINERARY]]\n\n## Budget\n\n[[COSTS]]"}
        days={days}
        hotels={hotels}
        costs={costs}
      />,
    );

    expect(card.days()).toBeInTheDocument();
    expect(card.hotels()).toBeInTheDocument();
    expect(card.costs()).toBeInTheDocument();
    // The markers themselves are replaced, never shown
    expect(screen.queryByText(/\[\[/)).not.toBeInTheDocument();
  });

  it("keeps the write-up's own prose around the cards", () => {
    render(<PlanBody content={"## Hotels\n\nWhere you sleep.\n\n[[HOTELS]]"} hotels={hotels} />);

    expect(screen.getByRole("heading", { name: "Hotels" })).toBeInTheDocument();
    expect(screen.getByText("Where you sleep.")).toBeInTheDocument();
    expect(card.hotels()).toBeInTheDocument();
  });

  // A reply only carries the cards its run produced: a hotels-only answer has no days, so nothing
  // should append a day-by-day plan under it
  it("shows no day cards when the reply carries none", () => {
    render(<PlanBody content={"## Hotels\n\nHotels in Tokyo\n\n[[HOTELS]]"} days={[]} hotels={hotels} costs={null} />);

    expect(card.hotels()).toBeInTheDocument();
    expect(card.days()).not.toBeInTheDocument();
    expect(card.costs()).not.toBeInTheDocument();
  });

  it("shows no cards at all for a plain answer", () => {
    render(<PlanBody content={"## Weather\n\nOvercast, 20°C."} days={[]} hotels={[]} costs={null} />);

    expect(screen.getByRole("heading", { name: "Weather" })).toBeInTheDocument();
    expect(card.days()).not.toBeInTheDocument();
    expect(card.hotels()).not.toBeInTheDocument();
  });

  it("still shows a card the write-up forgot to place, rather than losing it", () => {
    // The model occasionally drops a marker; the data is there, so it goes after the text
    render(<PlanBody content={"## Hotels\n\nWhere you sleep."} hotels={hotels} />);
    expect(card.hotels()).toBeInTheDocument();
  });

  it("renders the brief and the header card above the write-up", () => {
    const { container } = render(
      <PlanBody
        content={"## Weather\n\nOvercast."}
        brief={[{ label: "Duration", value: "5 days", assumed: true }]}
        header={{ destination: "Tokyo", summary: "Five days", dates: "May", duration: "5 days", origin: "Delhi", total: "Rs 2,00,000", image: "" }}
      />,
    );

    expect(screen.getByText("5 days")).toBeInTheDocument();
    expect(screen.getByText("Tokyo")).toBeInTheDocument();

    const text = container.textContent ?? "";
    expect(text.indexOf("Tokyo")).toBeLessThan(text.indexOf("Overcast."));
  });
});
