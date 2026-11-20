import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Import from "./Import.jsx";
import { imports } from "../api/endpoints.js";
import { ApiError } from "../api/client.js";
import { renderWithAuth } from "../test/renderWithAuth.jsx";

vi.mock("../api/endpoints.js", () => ({
  imports: { upload: vi.fn() },
}));

const WRITER = { permissions: ["imports:read", "imports:write"] };

const dryRunResult = {
  dry_run: true, batch_id: null, rows_total: 4, accepted: 2, duplicates: 1, conflicts: 0,
  rejected: 1, skipped_baseline: 0, skipped_gap: 0, resets_flagged: 0,
  problems: [{ row: 3, kind: "rejected", reason: "value: must be >= 0" }],
};

function chooseFile(name = "readings.csv") {
  const input = screen.getByLabelText(/readings file/i);
  const file = new File(["lab_name,timestamp,value,reading_type\n"], name, { type: "text/csv" });
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

describe("CSV import page", () => {
  beforeEach(() => {
    imports.upload.mockReset();
  });

  it("shows a dry-run summary with counts and row-level problems", async () => {
    imports.upload.mockResolvedValue(dryRunResult);
    renderWithAuth(<Import />, WRITER);
    chooseFile();
    fireEvent.click(screen.getByRole("button", { name: /check file/i }));

    await screen.findByText(/dry run: nothing was written/i);
    expect(imports.upload).toHaveBeenCalledWith(expect.any(File), { dryRun: true, intervalMinutes: 60 });
    expect(screen.getByText("Rejected")).toBeInTheDocument();
    expect(screen.getByText("value: must be >= 0")).toBeInTheDocument();
  });

  it("offers the real import only after a check finds accepted rows", async () => {
    imports.upload.mockResolvedValue(dryRunResult);
    renderWithAuth(<Import />, WRITER);
    chooseFile();
    fireEvent.click(screen.getByRole("button", { name: /check file/i }));
    expect(await screen.findByRole("button", { name: /import 2 readings/i })).toBeEnabled();
  });

  it("keeps the import button disabled when the check accepts nothing", async () => {
    imports.upload.mockResolvedValue({ ...dryRunResult, accepted: 0 });
    renderWithAuth(<Import />, WRITER);
    chooseFile();
    fireEvent.click(screen.getByRole("button", { name: /check file/i }));
    await screen.findByText(/dry run: nothing was written/i);
    expect(screen.getByRole("button", { name: /^import$/i })).toBeDisabled();
  });

  it("writes the file only when the user confirms, and reports the batch", async () => {
    imports.upload
      .mockResolvedValueOnce(dryRunResult)
      .mockResolvedValueOnce({ ...dryRunResult, dry_run: false, batch_id: 5, accepted: 2 });
    renderWithAuth(<Import />, WRITER);
    chooseFile();
    fireEvent.click(screen.getByRole("button", { name: /check file/i }));
    fireEvent.click(await screen.findByRole("button", { name: /import 2 readings/i }));

    await waitFor(() => expect(imports.upload).toHaveBeenCalledTimes(2));
    expect(imports.upload.mock.calls[1][1]).toEqual({ dryRun: false, intervalMinutes: 60 });
    expect(await screen.findByRole("heading", { name: /imported as batch 5/i })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("2 readings stored in batch 5");
  });

  it("shows API errors such as an invalid file", async () => {
    imports.upload.mockRejectedValue(new ApiError(422, "invalid_file", "CSV must contain the columns: lab_id or lab_name"));
    renderWithAuth(<Import />, WRITER);
    chooseFile();
    fireEvent.click(screen.getByRole("button", { name: /check file/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("CSV must contain");
  });

  it("is read-only for a role without import permission", () => {
    renderWithAuth(<Import />, { permissions: ["imports:read"] });
    expect(screen.getByText(/read-only/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/readings file/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: /check file/i })).toBeDisabled();
  });
});
