import { XIcon } from "lucide-react";
import { Dialog as SheetPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

const Sheet = (props: React.ComponentProps<typeof SheetPrimitive.Root>) => <SheetPrimitive.Root {...props} />;

function SheetContent({ className, children, ...props }: React.ComponentProps<typeof SheetPrimitive.Content>) {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Overlay className="fixed inset-0 z-50 bg-black/25 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
      <SheetPrimitive.Content
        className={cn(
          "fixed inset-y-0 right-0 z-50 flex h-full w-full flex-col bg-background shadow-2xl transition ease-in-out sm:max-w-[780px] data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=closed]:duration-200 data-[state=open]:animate-in data-[state=open]:slide-in-from-right data-[state=open]:duration-300",
          className,
        )}
        {...props}
      >
        {children}
        <SheetPrimitive.Close className="absolute top-5 right-5 grid size-9 place-items-center rounded-lg border bg-secondary hover:bg-accent">
          <XIcon className="size-4" />
          <span className="sr-only">Close</span>
        </SheetPrimitive.Close>
      </SheetPrimitive.Content>
    </SheetPrimitive.Portal>
  );
}

const SheetTitle = ({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Title>) => (
  <SheetPrimitive.Title className={cn("text-xl font-normal tracking-tight", className)} {...props} />
);
const SheetDescription = ({ className, ...props }: React.ComponentProps<typeof SheetPrimitive.Description>) => (
  <SheetPrimitive.Description className={cn("text-sm text-muted-foreground", className)} {...props} />
);

export { Sheet, SheetContent, SheetDescription, SheetTitle };
