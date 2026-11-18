import { Slider as SliderPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

function Slider({ className, ...props }: React.ComponentProps<typeof SliderPrimitive.Root>) {
  return (
    <SliderPrimitive.Root
      data-slot="slider"
      className={cn("relative flex w-full touch-none items-center select-none data-[disabled]:opacity-50", className)}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1 w-full grow overflow-hidden rounded-full bg-muted">
        <SliderPrimitive.Range className="absolute h-full bg-primary" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        aria-label="Materiality"
        className="block size-4 rounded-full border-2 border-primary bg-secondary shadow-sm transition hover:scale-110 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/15"
      />
    </SliderPrimitive.Root>
  );
}

export { Slider };
