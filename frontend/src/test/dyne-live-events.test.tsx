import React from "react";
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { render, screen, act, waitFor, fireEvent } from "@testing-library/react";
import { AirPointEngineProvider, useAirPointEngine } from "@/components/air-point/engine";
import { DyneLiveIsland } from "@/components/air-point/dyne-live-island";
import { DynamicIslandPreview } from "@/components/air-point/dynamic-island";
import { DyneStudio } from "@/components/air-point/dyne-studio/dyne-studio";
import {
  DEFAULT_BRIDGE_BASE_URL,
  DEFAULT_DYNE_APPEARANCE,
  mergeEvents,
  parseDyneEvent,
  resolveBridgeBaseUrl,
  sanitizeDyneAppearance,
  type AirPointEvent,
} from "@/lib/air-point-model";

/**
 * Unified Dyne event integration (migration Stage D/E).
 *
 * These tests drive the React subscriber with test-only fixtures that mirror
 * the schema published by backend/core/events.py. A fixture event is not a
 * webcam gesture: passing here proves the bridge contract and the island
 * wiring, not that the engine detects hands.
 */

type StatusPayload = Record<string, unknown>;

function statusPayload(events: StatusPayload[], overrides: StatusPayload = {}): StatusPayload {
  const lastId = events.reduce((max, ev) => Math.max(max, Number(ev["id"] ?? 0)), 0);
  return {
    running: true,
    tracking: "Right Hand",
    fps: 30,
    owner: "RIGHT",
    event_session: "s1",
    last_event_id: lastId,
    settings: {
      island_enabled: true,
      island_notifications_enabled: true,
      island_timer_enabled: true,
      island_autohide_enabled: true,
      island_hud_duration_s: 120,
      island_completion_duration_s: 2,
      island_position: "top-center",
      island_appearance: { ...DEFAULT_DYNE_APPEARANCE, accent: "Red" },
    },
    events,
    ...overrides,
  };
}

function dyneEvent(id: number, type: string, title: string, message: string, extra: StatusPayload = {}): StatusPayload {
  return {
    id,
    session: "s1",
    type: type.split(".")[1] ?? type,
    event_type: type,
    timestamp: 1_700_000_000 + id,
    time: `12:00:${String(id).padStart(2, "0")}`,
    source: "engine",
    title,
    message,
    priority: "normal",
    duration_s: 2,
    metadata: {},
    event: type.split(".")[1] ?? type,
    action: message,
    ...extra,
  };
}

function Probe() {
  const engine = useAirPointEngine();
  return (
    <div>
      <div data-testid="events-count">{engine.events.length}</div>
      <div data-testid="event-ids">{engine.events.map((e) => e.id).join(",")}</div>
      <div data-testid="event-stream">{engine.eventStream}</div>
      <div data-testid="island-position">{engine.islandPosition}</div>
      <div data-testid="island-accent">{engine.islandAppearance.accent}</div>
      <button type="button" onClick={() => void engine.refreshStatusNow()}>
        refresh
      </button>
      <DyneLiveIsland
        event={engine.liveNotification}
        appearance={engine.islandAppearance}
        position={engine.islandPosition}
        onDismiss={engine.dismissLiveNotification}
      />
    </div>
  );
}

function mockStatusSequence(payloads: StatusPayload[]) {
  let call = 0;
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const u = String(url);
    if (u.includes("/api/status")) {
      const payload = payloads[Math.min(call, payloads.length - 1)]!;
      call += 1;
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response("{}", { status: 200 });
  });
}

describe("Bridge discovery and event parsing", () => {
  it("accepts only loopback http origins for VITE_AIRPOINT_BRIDGE_URL", () => {
    expect(resolveBridgeBaseUrl(undefined)).toBe(DEFAULT_BRIDGE_BASE_URL);
    expect(resolveBridgeBaseUrl("http://127.0.0.1:52133/")).toBe("http://127.0.0.1:52133");
    expect(resolveBridgeBaseUrl("http://localhost:9000")).toBe("http://localhost:9000");
    expect(resolveBridgeBaseUrl("http://192.168.1.20:8765")).toBe(DEFAULT_BRIDGE_BASE_URL);
    expect(resolveBridgeBaseUrl("https://127.0.0.1:8765")).toBe(DEFAULT_BRIDGE_BASE_URL);
    expect(resolveBridgeBaseUrl("127.0.0.1:8765")).toBe(DEFAULT_BRIDGE_BASE_URL);
    expect(resolveBridgeBaseUrl("http://127.0.0.1:99999")).toBe(DEFAULT_BRIDGE_BASE_URL);
  });

  it("parses the unified schema and keeps legacy payloads readable", () => {
    const parsed = parseDyneEvent(dyneEvent(7, "tracking.lost", "Hand lost", "No hand for 350 ms"));
    expect(parsed).not.toBeNull();
    expect(parsed!.id).toBe("s1:7");
    expect(parsed!.type).toBe("tracking.lost");
    expect(parsed!.title).toBe("Hand lost");
    expect(parsed!.message).toBe("No hand for 350 ms");
    expect(parsed!.action).toBe("No hand for 350 ms");
    expect(parsed!.priority).toBe("normal");
    expect(parsed!.durationS).toBe(2);

    const legacy = parseDyneEvent({ time: "10:00:00", action: "Screenshot saved", event: "screenshot" }, 3);
    expect(legacy!.id).toBe("10:00:00-Screenshot saved-3");
    expect(legacy!.event).toBe("screenshot");
    expect(legacy!.type).toBeUndefined();
    expect(parseDyneEvent({ nothing: true })).toBeNull();
  });

  it("merges without duplicates, newest first, bounded", () => {
    const a = parseDyneEvent(dyneEvent(1, "engine.started", "AirPoint started", "up"))!;
    const b = parseDyneEvent(dyneEvent(2, "tracking.lost", "Hand lost", "lost"))!;
    const c = parseDyneEvent(dyneEvent(3, "tracking.recovered", "Hand reacquired", "back"))!;
    const merged = mergeEvents([b, a], [c, b], 50);
    expect(merged.map((e) => e.id)).toEqual(["s1:3", "s1:2", "s1:1"]);
    const bounded = mergeEvents(merged, [], 2);
    expect(bounded.map((e) => e.id)).toEqual(["s1:3", "s1:2"]);
  });

  it("validates persisted appearance objects", () => {
    const app = sanitizeDyneAppearance({ accent: "Purple", roundness: 999, texture: "Velvet", fontSize: 1 });
    expect(app.accent).toBe("Purple");
    expect(app.roundness).toBe(56);
    expect(app.texture).toBe(DEFAULT_DYNE_APPEARANCE.texture);
    expect(app.fontSize).toBe(18);
  });
});

describe("Live Dyne island driven by real bridge events", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows only events newer than the history present at connect, once, with host appearance", async () => {
    const history = [dyneEvent(1, "engine.started", "AirPoint started", "Engine running")];
    const later = [dyneEvent(2, "tracking.lost", "Hand lost", "No hand for 350 ms"), ...history];
    const fetchMock = mockStatusSequence([statusPayload(history), statusPayload(later), statusPayload(later)]);

    render(
      <AirPointEngineProvider>
        <Probe />
      </AirPointEngineProvider>
    );

    await waitFor(() => expect(screen.getByTestId("events-count").textContent).toBe("1"));
    // History at connect never raises the island
    expect(screen.queryByTestId("dyne-live-island")).toBeNull();
    expect(screen.getByTestId("island-accent").textContent).toBe("Red");

    await act(async () => {
      fireEvent.click(screen.getByText("refresh"));
    });
    await waitFor(() => expect(screen.getByTestId("events-count").textContent).toBe("2"));
    const island = await screen.findByTestId("dyne-live-island");
    expect(island).toHaveAttribute("data-live", "true");
    expect(island).toHaveAttribute("data-event-type", "tracking.lost");
    expect(island).toHaveAttribute("data-event-id", "s1:2");
    expect(island).toHaveAttribute("data-position", "top-center");
    expect(island.textContent).toContain("Hand lost");
    expect(island.textContent).toContain("Live");
    expect(island.textContent).not.toContain("PREVIEW");

    // The same payload again: no duplicate ids, no re-trigger
    await act(async () => {
      fireEvent.click(screen.getByText("refresh"));
    });
    expect(screen.getByTestId("events-count").textContent).toBe("2");
    expect(screen.getByTestId("event-ids").textContent).toBe("s1:2,s1:1");
    expect(fetchMock).toHaveBeenCalled();

    // Click dismisses the live island
    fireEvent.click(island.firstElementChild as HTMLElement);
    await waitFor(() => expect(screen.queryByTestId("dyne-live-island")).toBeNull());
  });

  it("stays silent when the host Dyne notifications switch is off, but still records the event", async () => {
    const history = [dyneEvent(1, "engine.started", "AirPoint started", "Engine running")];
    const later = [dyneEvent(2, "screenshot.captured", "Screenshot captured", "Saved shot.png"), ...history];
    const off = { island_enabled: true, island_notifications_enabled: false };
    mockStatusSequence([
      statusPayload(history, { settings: { ...(statusPayload([])["settings"] as StatusPayload), ...off } }),
      statusPayload(later, { settings: { ...(statusPayload([])["settings"] as StatusPayload), ...off } }),
    ]);

    render(
      <AirPointEngineProvider>
        <Probe />
      </AirPointEngineProvider>
    );
    await waitFor(() => expect(screen.getByTestId("events-count").textContent).toBe("1"));
    await act(async () => {
      fireEvent.click(screen.getByText("refresh"));
    });
    await waitFor(() => expect(screen.getByTestId("events-count").textContent).toBe("2"));
    expect(screen.queryByTestId("dyne-live-island")).toBeNull();
  });

  it("delivers Server-Sent Events (with ids) to the feed and the island", async () => {
    class FakeEventSource {
      static instances: FakeEventSource[] = [];
      url: string;
      onmessage: ((msg: { data: string }) => void) | null = null;
      onopen: (() => void) | null = null;
      onerror: (() => void) | null = null;
      constructor(url: string) {
        this.url = url;
        FakeEventSource.instances.push(this);
      }
      close() {}
    }
    const original = (globalThis as Record<string, unknown>)["EventSource"];
    (globalThis as Record<string, unknown>)["EventSource"] = FakeEventSource;
    try {
      mockStatusSequence([statusPayload([], { last_event_id: 4 })]);
      render(
        <AirPointEngineProvider>
          <Probe />
        </AirPointEngineProvider>
      );
      await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
      const es = FakeEventSource.instances[0]!;
      expect(es.url).toBe(`${DEFAULT_BRIDGE_BASE_URL}/api/events`);
      // Wait for the first status poll to prime the tracker (last_event_id = 4)
      await waitFor(() => expect(screen.getByTestId("island-position").textContent).toBe("top-center"));
      await act(async () => {
        es.onopen?.();
        es.onmessage?.({ data: JSON.stringify({ event: "connected", status: "ok", session: "s1", last_event_id: 4 }) });
        es.onmessage?.({ data: JSON.stringify(dyneEvent(5, "lock.failed", "Lock request failed", "Windows rejected the LockWorkStation request", { priority: "critical", duration_s: 4 })) });
      });
      expect(screen.getByTestId("event-stream").textContent).toBe("open");
      await waitFor(() => expect(screen.getByTestId("events-count").textContent).toBe("1"));
      const island = await screen.findByTestId("dyne-live-island");
      expect(island).toHaveAttribute("data-event-type", "lock.failed");
      expect(island.textContent).toContain("Lock request failed");
      // A replayed duplicate (same id) changes nothing
      await act(async () => {
        es.onmessage?.({ data: JSON.stringify(dyneEvent(5, "lock.failed", "Lock request failed", "dup")) });
      });
      expect(screen.getByTestId("events-count").textContent).toBe("1");
    } finally {
      (globalThis as Record<string, unknown>)["EventSource"] = original;
    }
  });
});

describe("Preview versus live distinction", () => {
  it("keeps Studio previews labelled as previews and the live island labelled live", () => {
    const { container: previewContainer } = render(<DynamicIslandPreview state="screenshot" volume={50} />);
    expect(previewContainer.textContent).toContain("PREVIEW");
    const event: AirPointEvent = {
      id: "s1:9",
      event: "screenshot",
      action: "Saved shot.png",
      time: "12:00:09",
      type: "screenshot.captured",
      sequence: 9,
      session: "s1",
      title: "Screenshot captured",
      message: "Saved shot.png",
      priority: "high",
      durationS: 2.5,
    };
    const { container } = render(
      <DyneLiveIsland event={event} appearance={DEFAULT_DYNE_APPEARANCE} position="bottom-center" />
    );
    const island = container.querySelector('[data-testid="dyne-live-island"]')!;
    expect(island).toHaveAttribute("data-live", "true");
    expect(island).toHaveAttribute("data-position", "bottom-center");
    expect(island.textContent).toContain("Screenshot captured");
    expect(island.textContent).not.toContain("PREVIEW");
  });

  it("Dyne Studio applies a look only on explicit request and reports the position", async () => {
    const setIslandSettings = vi.fn(async () => true);
    const setIslandAppearance = vi.fn(async () => true);
    const setIslandPosition = vi.fn(async () => true);
    render(
      <DyneStudio
        hostAdapter={{ setIslandSettings, setIslandAppearance, setIslandPosition }}
        capabilities={{ enabled: "read-write", notificationsEnabled: "read-write" }}
        desktopSettings={{
          enabled: true,
          notificationsEnabled: true,
          timerEnabled: true,
          autohideEnabled: true,
          hudDurationS: 120,
          completionDurationS: 2,
        }}
        hostConnected
        settingsSynced
        islandPosition="top-right"
        appliedAppearance={{ ...DEFAULT_DYNE_APPEARANCE, accent: "Purple" }}
      />
    );
    // Enter the main options layer by clicking the central capsule
    fireEvent.click(screen.getByRole("button", { name: /open main options/i }));
    const apply = await screen.findByTestId("dyne-apply-look");
    expect(screen.getByTestId("dyne-look-status").textContent).toContain("PREVIEW");
    expect(setIslandAppearance).not.toHaveBeenCalled();
    fireEvent.click(apply);
    await waitFor(() => expect(setIslandAppearance).toHaveBeenCalledTimes(1));
    const sent = setIslandAppearance.mock.calls[0]![0] as { accent: string };
    expect(typeof sent.accent).toBe("string");
    // Loading the live look copies it into the preview capsule and marks it live
    fireEvent.click(screen.getByTestId("dyne-load-live-look"));
    await waitFor(() => expect(screen.getByTestId("dyne-look-status").textContent).toContain("LIVE"));
    expect(setIslandPosition).not.toHaveBeenCalled();
  });
});
