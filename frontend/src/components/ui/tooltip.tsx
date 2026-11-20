import { Tooltip as TooltipPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

const TooltipProvider = (props: React.ComponentProps<typeof TooltipPrimitive.Provider>) => (
  <TooltipPrimitive.Provider delayDuration={150} {...props} />
);

// Touch screens have no hover, so a tap on the trigger opens and closes the tooltip (A42).
const TapToggle = React.createContext<{ open: boolean; change: (open: boolean) => void } | null>(null);

function Tooltip({ open: openProp, onOpenChange, ...props }: React.ComponentProps<typeof TooltipPrimitive.Root>) {
  const [own, setOwn] = React.useState(false);
  const open = openProp ?? own;
  const change = React.useCallback(
    (next: boolean) => {
      setOwn(next);
      onOpenChange?.(next);
    },
    [onOpenChange],
  );
  const toggle = React.useMemo(() => ({ open, change }), [open, change]);
  return (
    <TapToggle.Provider value={toggle}>
      <TooltipPrimitive.Root open={open} onOpenChange={change} {...props} />
    </TapToggle.Provider>
  );
}

function TooltipTrigger({ onPointerDown, onClick, ...props }: React.ComponentProps<typeof TooltipPrimitive.Trigger>) {
  const tap = React.useContext(TapToggle);
  // Open or not when a finger touched down (null for a mouse or a key press).
  const openAtTouch = React.useRef<boolean | null>(null);
  return (
    <TooltipPrimitive.Trigger
      {...props}
      onPointerDown={(e) => {
        openAtTouch.current = e.pointerType === "mouse" ? null : !!tap?.open;
        onPointerDown?.(e);
      }}
      onClick={(e) => {
        onClick?.(e);
        const was = openAtTouch.current;
        openAtTouch.current = null;
        if (was === null || !tap) return;
        // The tap is for the tooltip, not for a row or card around it.
        e.stopPropagation();
        // After Radix's own handler, which closes the tooltip on a click.
        queueMicrotask(() => tap.change(!was));
      }}
    />
  );
}

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
