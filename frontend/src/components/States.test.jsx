import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EmptyState, ErrorBanner, LoadingState } from "./States.jsx";

describe("shared state components", () => {
  it("shows the API error message and code, and offers a retry", () => {
    const onRetry = vi.fn();
    render(<ErrorBanner error={{ message: "lab not found", code: "lab_not_found" }} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("lab not found");
    expect(screen.getByText("lab_not_found")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when there is no error", () => {
    const { container } = render(<ErrorBanner error={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("explains an empty result with a title and description", () => {
    render(<EmptyState title="No readings">Import a file to start.</EmptyState>);
    expect(screen.getByText("No readings")).toBeInTheDocument();
    expect(screen.getByText("Import a file to start.")).toBeInTheDocument();
  });

  it("announces loading to assistive technology", () => {
    render(<LoadingState label="Loading labs" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading labs");
  });
});
