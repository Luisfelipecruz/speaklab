"use client";

/**
 * The theme control: light, dark, or whatever the operating system says.
 *
 * **It starts as "system" on the server and corrects itself on mount, deliberately.** The
 * stored choice lives in `localStorage`, which the server cannot see, so rendering the
 * real state during SSR is impossible — and rendering a guess produces a hydration
 * mismatch that React resolves by blanking the subtree. The colours themselves do not
 * wait for this: a script in `<head>` has already set the class before the first paint.
 * What waits is only which of the three items shows a tick.
 *
 * A menu rather than a two-way switch, because a switch cannot express "system" and a
 * product that silently drops that option is one that ignores a preference the reader
 * already stated to their machine.
 */

import { useEffect, useState } from "react";
import { LaptopIcon, MoonIcon, SunIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { applyTheme, readStoredTheme, storeTheme, type Theme } from "@/lib/theme";

const OPTIONS: { value: Theme; label: string; icon: typeof SunIcon }[] = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "System", icon: LaptopIcon },
];

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    setTheme(readStoredTheme());
  }, []);

  const choose = (next: Theme) => {
    setTheme(next);
    storeTheme(next);
    applyTheme(next);
  };

  const Current = OPTIONS.find((option) => option.value === theme)?.icon ?? LaptopIcon;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Theme: ${theme}`}>
          <Current />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top">
        {OPTIONS.map((option) => (
          <DropdownMenuItem
            key={option.value}
            onSelect={() => choose(option.value)}
            aria-current={theme === option.value ? "true" : undefined}
          >
            <option.icon />
            {option.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
