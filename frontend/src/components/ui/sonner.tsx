import { Toaster as Sonner, type ToasterProps } from "sonner";

const Toaster = (props: ToasterProps) => (
  <Sonner
    position="top-right"
    toastOptions={{
      classNames: {
        toast: "!rounded-xl !border-border !bg-secondary !text-foreground !shadow-lg",
        description: "!text-muted-foreground",
      },
    }}
    {...props}
  />
);

export { Toaster };
