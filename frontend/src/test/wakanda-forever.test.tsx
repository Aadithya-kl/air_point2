import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, act } from "@testing-library/react";
import React, { useState } from "react";
import { WakandaCapsule } from "@/components/air-point/wakanda-capsule";
import { WakandaSimulationDeck } from "@/components/air-point/wakanda-simulation-deck";
import { GestureDiagram } from "@/components/air-point/illustrations";
import { DynamicIslandPreview } from "@/components/air-point/dynamic-island";
import { GESTURE_SPECS } from "@/lib/air-point-model";

describe("Wakanda Forever V3 Capsule & Integration", () => {
  it("renders only 'WAKANDA FOREVER' as interior capsule copy (text-only V3 rule)", () => {
    render(<WakandaCapsule phase="holding" progress={45} />);
    const capsule = screen.getByTestId("wakanda-capsule");
    expect(capsule).toBeInTheDocument();
    expect(capsule).toHaveTextContent("WAKANDA FOREVER");
    // Ensure no countdowns, mascots, or state words inside the capsule
    expect(capsule.textContent).not.toMatch(
      /ARMED|DISARMED|HOLDING|COMPLETE|LOCK SEQUENCE|PREVIEW|CANCELLED|\d+%/i
    );
  });

  it("applies phase classes and bounds progress correctly", () => {
    const { rerender } = render(<WakandaCapsule phase="disarmed" progress={0} />);
    expect(screen.getByTestId("wakanda-capsule")).toHaveClass("phase-disarmed");

    rerender(<WakandaCapsule phase="armed" progress={0} />);
    expect(screen.getByTestId("wakanda-capsule")).toHaveClass("phase-armed");

    rerender(<WakandaCapsule phase="holding" progress={75} />);
    expect(screen.getByTestId("wakanda-capsule")).toHaveClass("phase-holding");

    rerender(<WakandaCapsule phase="complete" progress={100} />);
    expect(screen.getByTestId("wakanda-capsule")).toHaveClass("phase-complete");
  });

  it("WakandaSimulationDeck requires arming before simulation", () => {
    const Wrapper = () => {
      const [isArmed, setIsArmed] = useState(false);
      return (
        <WakandaSimulationDeck
          isArmed={isArmed}
          onToggleArm={() => setIsArmed(!isArmed)}
        />
      );
    };
    render(<Wrapper />);

    const simBtn = screen.getByRole("button", {
      name: /simulate crossed-arm gesture/i,
    });
    expect(simBtn).toBeDisabled();

    const armBtn = screen.getByRole("button", { name: /arm feature/i });
    fireEvent.click(armBtn);

    expect(screen.getByRole("button", { name: /disarm feature/i })).toBeInTheDocument();
    expect(simBtn).toBeEnabled();
  });

  it("WakandaSimulationDeck shows preview-only safety disclosure", () => {
    render(
      <WakandaSimulationDeck isArmed={false} onToggleArm={() => {}} />
    );
    expect(
      screen.getByText(/does not access your camera/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Preview only — safe by design/i)
    ).toBeInTheDocument();
  });

  it("GestureDiagram renders crossed-arm SVG shape for wakanda-forever", () => {
    const { container } = render(
      <GestureDiagram gestureId="wakanda-forever" size="lg" />
    );
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute(
      "data-gesture-shape",
      "crossed-arms-wakanda-forever"
    );
  });

  it("DynamicIslandPreview renders wakanda-hold and wakanda-forever states", () => {
    const { rerender } = render(
      <DynamicIslandPreview state="wakanda-hold" volume={50} countdownSeconds={1.5} />
    );
    expect(screen.getByText(/WAKANDA FOREVER · 1.5s/i)).toBeInTheDocument();

    rerender(
      <DynamicIslandPreview state="wakanda-forever" volume={50} />
    );
    expect(screen.getByText(/WAKANDA FOREVER · LOCKED/i)).toBeInTheDocument();
  });

  it("Wakanda Forever is configured as a disabled-by-default System Action", () => {
    const spec = GESTURE_SPECS.find((g) => g.id === "wakanda-forever");
    expect(spec).toBeDefined();
    expect(spec?.category).toBe("System Actions");
    expect(spec?.anatomicalAnchor).toContain("Crossed");
    expect(spec?.windowsAction).toContain("LockWorkStation");
  });
});
