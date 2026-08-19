import { Drawer as DrawerPrimitive } from 'vaul'
import { forwardRef } from 'react'
import { cn } from '../../lib/utils'

// Shadcn-style Drawer (vaul) pinned to the right edge (design brief Phase 4: "trượt vào từ cạnh
// phải màn hình") - vaul defaults to a bottom sheet, `direction="right"` on the Root is what
// changes that.
export function Drawer({ shouldScaleBackground = true, ...props }) {
  return <DrawerPrimitive.Root direction="right" shouldScaleBackground={shouldScaleBackground} {...props} />
}

export const DrawerTrigger = DrawerPrimitive.Trigger
export const DrawerPortal = DrawerPrimitive.Portal
export const DrawerClose = DrawerPrimitive.Close

export const DrawerOverlay = forwardRef(({ className, ...props }, ref) => (
  <DrawerPrimitive.Overlay ref={ref} className={cn('fixed inset-0 z-50 bg-black/60 backdrop-blur-sm', className)} {...props} />
))
DrawerOverlay.displayName = DrawerPrimitive.Overlay.displayName

export const DrawerContent = forwardRef(({ className, children, ...props }, ref) => (
  <DrawerPortal>
    <DrawerOverlay />
    <DrawerPrimitive.Content
      ref={ref}
      className={cn(
        'fixed inset-y-0 right-0 z-50 flex h-full w-full max-w-md flex-col border-l border-white/10 bg-background/90 backdrop-blur-md shadow-glow outline-none',
        className
      )}
      {...props}
    >
      <div className="mx-auto mt-4 h-1.5 w-10 shrink-0 rounded-full bg-white/15 md:hidden" />
      {children}
    </DrawerPrimitive.Content>
  </DrawerPortal>
))
DrawerContent.displayName = 'DrawerContent'

export const DrawerHeader = ({ className, ...props }) => <div className={cn('grid gap-1.5 p-6 pb-2 text-left', className)} {...props} />

export const DrawerFooter = ({ className, ...props }) => (
  <div className={cn('mt-auto flex flex-col gap-2 border-t border-white/10 p-6', className)} {...props} />
)

export const DrawerTitle = forwardRef(({ className, ...props }, ref) => (
  <DrawerPrimitive.Title ref={ref} className={cn('text-lg font-semibold leading-none tracking-tight text-foreground', className)} {...props} />
))
DrawerTitle.displayName = DrawerPrimitive.Title.displayName

export const DrawerDescription = forwardRef(({ className, ...props }, ref) => (
  <DrawerPrimitive.Description ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} />
))
DrawerDescription.displayName = DrawerPrimitive.Description.displayName
