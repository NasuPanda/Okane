import { Slider as SliderPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

function Slider({
  className,
  tone = "default",
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root> & { tone?: "default" | "signal" }) {
  const signal = tone === "signal";
  return (
    <SliderPrimitive.Root
      data-slot="slider"
      className={cn("relative flex w-full touch-none items-center select-none data-[disabled]:opacity-50", className)}
      {...props}
    >
      <SliderPrimitive.Track
        className={cn("relative h-1.5 w-full grow overflow-hidden rounded-full", signal ? "bg-white/20" : "bg-muted")}
      >
        <SliderPrimitive.Range className={cn("absolute h-full", signal ? "bg-signal" : "bg-primary")} />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        aria-label={props["aria-label"] ?? "Value"}
        className={cn(
          "block size-5 rounded-full border-2 shadow-md transition hover:scale-110 focus-visible:outline-none focus-visible:ring-4",
          signal
            ? "border-signal bg-[#0d0d0f] focus-visible:ring-signal/30"
            : "border-primary bg-secondary focus-visible:ring-ring/15",
        )}
      />
    </SliderPrimitive.Root>
  );
}

export { Slider };
