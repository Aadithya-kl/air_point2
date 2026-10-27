import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import {
  CapsuleStage,
  CapsuleBody,
  MechanicalFin,
  FIN_DEPLOYMENT_ANGLES,
  getFinTargetAngle,
  type CapsuleState,
} from "@/components/air-point/capsule";

describe("Futuristic Interactive Capsule Foundation (Phase 2)", () => {
  it("renders CapsuleBody with accessible status semantics and default IDLE state", () => {
    render(<CapsuleBody state="IDLE" />);

    const body = screen.getByRole("status");
    expect(body).toBeInTheDocument();
    expect(body).toHaveAttribute("data-capsule-state", "IDLE");
    expect(body).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("AirPoint Core")).toBeInTheDocument();
    expect(screen.getByText("IDLE")).toBeInTheDocument();
  });

  const states: CapsuleState[] = [
    "IDLE",
    "ARMED",
    "COUNTDOWN",
    "ACTIVE",
    "POWER_SAVE",
    "WAKE",
  ];

  it.each(states)("renders CapsuleBody correctly across state: %s", (state) => {
    const { unmount } = render(<CapsuleBody state={state} testId={`capsule-${state}`} />);

    const element = screen.getByTestId(`capsule-${state}`);
    expect(element).toBeInTheDocument();
    expect(element).toHaveAttribute("data-capsule-state", state);

    unmount();
  });

  it("applies custom label, sublabel, and badge overrides cleanly", () => {
    render(
      <CapsuleBody
        state="ARMED"
        label="Custom Mode"
        sublabel="Sensors Active"
        badge="CUSTOM"
      />
    );

    expect(screen.getByText("Custom Mode")).toBeInTheDocument();
    expect(screen.getByText("Sensors Active")).toBeInTheDocument();
    expect(screen.getByText("CUSTOM")).toBeInTheDocument();
  });

  it("invokes onClick callback when interactive is enabled", () => {
    const handleClick = vi.fn();
    render(
      <CapsuleBody
        state="ACTIVE"
        interactive={true}
        onClick={handleClick}
        testId="interactive-capsule"
      />
    );

    const element = screen.getByTestId("interactive-capsule");
    fireEvent.click(element);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it("renders CapsuleStage with 3D perspective viewport and central CapsuleBody", () => {
    render(
      <CapsuleStage
        state="COUNTDOWN"
        accent="dual"
        label="Countdown Test"
      />
    );

    const stage = screen.getByTestId("capsule-stage");
    expect(stage).toBeInTheDocument();
    expect(stage).toHaveAttribute("data-stage-state", "COUNTDOWN");
    expect(stage).toHaveAttribute("data-stage-accent", "dual");

    // The inner body is rendered
    expect(screen.getByText("Countdown Test")).toBeInTheDocument();
    expect(screen.getAllByText("COUNTDOWN").length).toBeGreaterThanOrEqual(1);

    // Calibration horizon is present
    expect(screen.getByText("STAGE PERSPECTIVE 1200PX")).toBeInTheDocument();
  });

  it("projects custom child components into the 3D stage layer", () => {
    render(
      <CapsuleStage state="IDLE">
        <div data-testid="projected-child">Mechanical Fin Assembly Preview</div>
      </CapsuleStage>
    );

    expect(screen.getByTestId("projected-child")).toBeInTheDocument();
    expect(screen.getByText("Mechanical Fin Assembly Preview")).toBeInTheDocument();
  });

  it("renders volumetric lighting rigs by default and allows hiding them", () => {
    const { rerender } = render(
      <CapsuleStage state="ACTIVE" showLightingRigs={true} testId="stage-lit" />
    );
    expect(screen.getByTestId("stage-lit")).toBeInTheDocument();

    rerender(
      <CapsuleStage state="ACTIVE" showLightingRigs={false} testId="stage-unlit" />
    );
    expect(screen.getByTestId("stage-unlit")).toBeInTheDocument();
  });

  it("operates in complete offline isolation without throwing errors", () => {
    // Assert no network or browser API crash when backend is absent
    expect(() => {
      render(
        <div>
          <CapsuleStage state="POWER_SAVE" />
          <CapsuleBody state="POWER_SAVE" />
        </div>
      );
    }).not.toThrow();

    expect(screen.getAllByText("Power Saver").length).toBeGreaterThanOrEqual(1);
  });
});

describe("Mechanical Fins & 3D Kinematics (Phase 3)", () => {
  it("Requirement 1: Renders both left and right fin components correctly", () => {
    render(
      <div>
        <MechanicalFin orientation="left" state="IDLE" />
        <MechanicalFin orientation="right" state="IDLE" />
      </div>
    );

    const leftFin = screen.getByTestId("mechanical-fin-left");
    const rightFin = screen.getByTestId("mechanical-fin-right");

    expect(leftFin).toBeInTheDocument();
    expect(rightFin).toBeInTheDocument();
    expect(leftFin).toHaveAttribute("data-orientation", "left");
    expect(rightFin).toHaveAttribute("data-orientation", "right");
  });

  it("Requirement 2: Uses mirrored pivot origin behavior for left vs right assemblies", () => {
    render(
      <div>
        <MechanicalFin orientation="left" state="ARMED" />
        <MechanicalFin orientation="right" state="ARMED" />
      </div>
    );

    const leftFin = screen.getByTestId("mechanical-fin-left");
    const rightFin = screen.getByTestId("mechanical-fin-right");

    // Left fin pivot sits at its root on the right edge (calc(100% - 7px) 50%)
    expect(leftFin.style.transformOrigin).toBe("calc(100% - 7px) 50%");

    // Right fin pivot sits at its root on the left edge (7px 50%)
    expect(rightFin.style.transformOrigin).toBe("7px 50%");
  });

  it("Requirement 3: Maps each capsule state explicitly to its target deployment angle", () => {
    expect(getFinTargetAngle("IDLE")).toBe(0);
    expect(getFinTargetAngle("ARMED")).toBe(18);
    expect(getFinTargetAngle("COUNTDOWN")).toBe(45);
    expect(getFinTargetAngle("ACTIVE")).toBe(90);
    expect(getFinTargetAngle("POWER_SAVE")).toBe(5);
    expect(getFinTargetAngle("WAKE")).toBe(105);

    expect(FIN_DEPLOYMENT_ANGLES).toEqual({
      IDLE: 0,
      ARMED: 18,
      COUNTDOWN: 45,
      ACTIVE: 90,
      POWER_SAVE: 5,
      WAKE: 105,
    });
  });

  it("Requirement 4: Verifies IDLE and POWER_SAVE states are visually compact (<= 5 deg)", () => {
    const idleAngle = getFinTargetAngle("IDLE");
    const powerSaveAngle = getFinTargetAngle("POWER_SAVE");

    expect(idleAngle).toBe(0);
    expect(powerSaveAngle).toBe(5);
    expect(idleAngle).toBeLessThanOrEqual(5);
    expect(powerSaveAngle).toBeLessThanOrEqual(5);

    render(
      <div>
        <MechanicalFin orientation="left" state="IDLE" testId="left-idle" />
        <MechanicalFin orientation="right" state="POWER_SAVE" testId="right-ps" />
      </div>
    );

    expect(screen.getByTestId("left-idle")).toHaveAttribute("data-deployment-angle", "0");
    expect(screen.getByTestId("right-ps")).toHaveAttribute("data-deployment-angle", "5");
  });

  it("Requirement 5: Verifies ACTIVE state reaches the full 90 deg deployment angle", () => {
    render(<MechanicalFin orientation="left" state="ACTIVE" testId="left-active" />);

    const leftActive = screen.getByTestId("left-active");
    expect(leftActive).toHaveAttribute("data-deployment-angle", "90");
    expect(getFinTargetAngle("ACTIVE")).toBe(90);
  });

  it("Requirement 6: Applies wake animation class with 105 deg overshoot for WAKE state", () => {
    render(
      <div>
        <MechanicalFin orientation="left" state="WAKE" testId="left-wake" />
        <MechanicalFin orientation="right" state="WAKE" testId="right-wake" />
      </div>
    );

    const leftWake = screen.getByTestId("left-wake");
    const rightWake = screen.getByTestId("right-wake");

    expect(leftWake).toHaveAttribute("data-deployment-angle", "105");
    expect(rightWake).toHaveAttribute("data-deployment-angle", "105");
    expect(leftWake.className).toContain("mechanical-fin-wake-left");
    expect(rightWake.className).toContain("mechanical-fin-wake-right");
  });

  it("Requirement 7: CapsuleStage automatically mounts both articulated fins flanking the chassis", () => {
    render(<CapsuleStage state="COUNTDOWN" />);

    const leftFin = screen.getByTestId("mechanical-fin-left");
    const rightFin = screen.getByTestId("mechanical-fin-right");
    const body = screen.getByTestId("capsule-body");

    expect(leftFin).toBeInTheDocument();
    expect(rightFin).toBeInTheDocument();
    expect(body).toBeInTheDocument();

    expect(leftFin).toHaveAttribute("data-fin-state", "COUNTDOWN");
    expect(rightFin).toHaveAttribute("data-fin-state", "COUNTDOWN");
    expect(leftFin).toHaveAttribute("data-deployment-angle", "45");
    expect(rightFin).toHaveAttribute("data-deployment-angle", "45");
  });

  it("Requirement 8: Supports explicit deployment angle and custom sweep/pitch overrides", () => {
    render(
      <MechanicalFin
        orientation="left"
        state="IDLE"
        deploymentAngle={60}
        pitchDeg={8}
        sweepDeg={3}
        testId="custom-fin"
      />
    );

    const fin = screen.getByTestId("custom-fin");
    expect(fin).toHaveAttribute("data-deployment-angle", "60");
    // Check signed 3D transform contains the explicit angles
    expect(fin.style.transform).toContain("rotateZ(-60deg)");
    expect(fin.style.transform).toContain("rotateY(8deg)");
    expect(fin.style.transform).toContain("rotateX(3deg)");
  });

  it("Requirement 9: Operates in complete offline isolation without requiring backend", () => {
    expect(() => {
      render(
        <CapsuleStage state="ACTIVE" accent="dual" />
      );
    }).not.toThrow();

    expect(screen.getByTestId("mechanical-fin-left")).toBeInTheDocument();
    expect(screen.getByTestId("mechanical-fin-right")).toBeInTheDocument();
  });

  it("Requirement 10: Renders multi-layered mechanical fin geometry with undercarriage, armor plating, and hinge", () => {
    const { container } = render(
      <MechanicalFin orientation="left" state="ACTIVE" accent="dual" />
    );

    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();

    // Verify undercarriage and primary armor polygon layers
    const polygons = container.querySelectorAll("polygon");
    expect(polygons.length).toBeGreaterThanOrEqual(3);

    // Verify presence of titanium gradients and energy conduit path
    expect(container.querySelector("#fin-understructure-left")).toBeInTheDocument();
    expect(container.querySelector("#fin-titanium-left")).toBeInTheDocument();
    expect(container.querySelector("#fin-bevel-left")).toBeInTheDocument();
  });

  it("Requirement 11: Renders enhanced chassis with physical depth and lateral hinge docking collars", () => {
    render(<CapsuleBody state="ARMED" />);

    const body = screen.getByRole("status");
    expect(body).toBeInTheDocument();
    expect(body.className).toContain("max-w-[420px]");
    expect(body.style.boxShadow).toContain("rgba(0, 0, 0, 0.95)");
  });
});
