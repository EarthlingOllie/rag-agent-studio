import { render, screen } from "@testing-library/react";

import { TopBarActions } from "./TopBarActions";

test("outside the Organisation shell there is no top bar, so a page's top bar actions show nowhere", () => {
  render(
    <TopBarActions>
      <button type="button">Publish</button>
    </TopBarActions>,
  );

  expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
});
