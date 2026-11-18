import { Tooltip as TooltipPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

const TooltipProvider = (props: React.ComponentProps<typeof TooltipPrimitive.Provider>) => (
  <TooltipPrimitive.Provider delayDuration={150} {...props} />
);
const Tooltip = (props: React.ComponentProps<typeof TooltipPrimitive.Root>) => <TooltipPrimitive.Root {...props} />;
const TooltipTrigger = (props: React.ComponentProps<typeof TooltipPrimitive.Trigger>) => (
  <TooltipPrimitive.Trigger {...props} />
);

function TooltipContent({ className, sideOffset = 6, ...props }: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 max-w-xs rounded-lg bg-dock px-3 py-1.5 text-xs text-white animate-in fade-in-0 zoom-in-95",
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Portal>
  );
}

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger };
