import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EntryForm } from "./EntryForm";

function fill(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function fillRequired() {
  fill(/Symbol/, "MNQ");
  fill(/Entered at/, "2025-10-09T10:53:50");
  fill(/Entry price/, "21400");
  fill(/Size/, "1");
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("EntryForm", () => {
  it("rejects an exit before the entry without calling the API", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn();
    render(<EntryForm onCreated={onCreated} />);

    fillRequired();
    fill(/Exited at/, "2025-10-09T09:53:50");
    fireEvent.click(screen.getByRole("button", { name: /Log trade/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "exit time must be at or after entry time",
    );
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("POSTs the entry with *_ns nanoseconds and refetches on success", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 201,
      text: async () => '{"id":1}',
    }));
    vi.stubGlobal("fetch", fetchMock);
    const onCreated = vi.fn();
    render(<EntryForm onCreated={onCreated} />);

    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: /Log trade/ }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledOnce());
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/backend/journal");
    const body = String(init.body);
    // Local wall time → absolute ns; exact digits depend on the test TZ, so
    // assert the shape: an unquoted 19-digit integer.
    expect(body).toMatch(/"entered_at_ns":\d{19}[,}]/);
    expect(body).toContain('"symbol":"MNQ"');
    expect(body).toContain('"exited_at_ns":null');
  });

  it("surfaces the backend 422 detail", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 422,
        text: async () =>
          '{"detail":[{"type":"value_error","loc":["body"],"msg":"exited_at_ns must be >= entered_at_ns"}]}',
      })),
    );
    render(<EntryForm onCreated={vi.fn()} />);

    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: /Log trade/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "body: exited_at_ns must be >= entered_at_ns",
    );
  });
});
