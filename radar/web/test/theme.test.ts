import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// The stylesheet is read from the package root (npm test runs there), so the token sets
// are checked as the browser would load them, without a running page.
const css = readFileSync(resolve("src/styles/radar.css"), "utf-8");

/** Custom property names declared in a block of CSS. */
function tokenNames(block: string): string[] {
  return Array.from(block.matchAll(/--([a-z0-9-]+):/g), (match) => match[1] ?? "");
}

const lightBlock = /:root \{([\s\S]*?)\n\}/.exec(css)?.[1] ?? "";
const darkBlock = /@media \(prefers-color-scheme: dark\) \{\s*:root \{([\s\S]*?)\n {2}\}/.exec(css)?.[1] ?? "";

describe("light and dark themes (6.1)", () => {
  it("loads a light token set by default and a dark token set under the dark preference", () => {
    expect(lightBlock.length).toBeGreaterThan(0);
    expect(darkBlock.length).toBeGreaterThan(0);
    expect(css).toMatch(/@media \(prefers-color-scheme: dark\)/);
    expect(lightBlock).toContain("color-scheme: light");
    expect(darkBlock).toContain("color-scheme: dark");
  });

  it("defines the same colour tokens in both themes", () => {
    const light = tokenNames(lightBlock).filter((name) => /^(color|persona)-/.test(name)).sort();
    const dark = tokenNames(darkBlock).filter((name) => /^(color|persona)-/.test(name)).sort();
    expect(light.length).toBeGreaterThan(20);
    expect(dark).toEqual(light);
  });

  it("defines every colour token the stylesheet uses in both themes", () => {
    const used = new Set(Array.from(css.matchAll(/var\(--((?:color|persona)-[a-z0-9-]+)\)/g), (m) => m[1] ?? ""));
    const light = new Set(tokenNames(lightBlock));
    const dark = new Set(tokenNames(darkBlock));
    for (const name of used) {
      expect(light.has(name), `light ${name}`).toBe(true);
      expect(dark.has(name), `dark ${name}`).toBe(true);
    }
  });
});
