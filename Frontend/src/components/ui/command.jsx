import { Command as CommandPrimitive } from 'cmdk'
import { Search } from 'lucide-react'
import { forwardRef } from 'react'
import { cn } from '../../lib/utils'
import { Dialog, DialogContent } from './dialog'

export const Command = forwardRef(({ className, ...props }, ref) => (
  <CommandPrimitive
    ref={ref}
    className={cn('flex h-full w-full flex-col overflow-hidden rounded-lg bg-transparent text-foreground', className)}
    {...props}
  />
))
Command.displayName = CommandPrimitive.displayName

// The floating, glassy Cmd+K palette itself - a Dialog whose content IS the Command tree, per
// design brief Phase 2 ("thanh tìm kiếm nổi giữa màn hình, nền kính mờ").
export function CommandDialog({ open, onOpenChange, children }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent showClose={false} className="max-w-xl overflow-hidden p-0 shadow-glow">
        <Command className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group]]:px-2 [&_[cmdk-input-wrapper]_svg]:h-5 [&_[cmdk-input-wrapper]_svg]:w-5 [&_[cmdk-input]]:h-12 [&_[cmdk-item]]:px-2 [&_[cmdk-item]]:py-3 [&_[cmdk-item]_svg]:h-5 [&_[cmdk-item]_svg]:w-5">
          {children}
        </Command>
      </DialogContent>
    </Dialog>
  )
}

export const CommandInput = forwardRef(({ className, ...props }, ref) => (
  <div className="flex items-center gap-2 border-b border-white/10 px-4" cmdk-input-wrapper="">
    <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
    <CommandPrimitive.Input
      ref={ref}
      className={cn(
        'flex h-11 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      {...props}
    />
  </div>
))
CommandInput.displayName = CommandPrimitive.Input.displayName

export const CommandList = forwardRef(({ className, ...props }, ref) => (
  <CommandPrimitive.List ref={ref} className={cn('max-h-[320px] overflow-y-auto overflow-x-hidden p-2', className)} {...props} />
))
CommandList.displayName = CommandPrimitive.List.displayName

export const CommandEmpty = forwardRef((props, ref) => (
  <CommandPrimitive.Empty ref={ref} className="py-6 text-center text-sm text-muted-foreground" {...props} />
))
CommandEmpty.displayName = CommandPrimitive.Empty.displayName

export const CommandGroup = forwardRef(({ className, ...props }, ref) => (
  <CommandPrimitive.Group
    ref={ref}
    className={cn('overflow-hidden p-1 text-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs', className)}
    {...props}
  />
))
CommandGroup.displayName = CommandPrimitive.Group.displayName

export const CommandItem = forwardRef(({ className, ...props }, ref) => (
  <CommandPrimitive.Item
    ref={ref}
    className={cn(
      'relative flex cursor-pointer select-none items-center gap-2 rounded-md px-2 py-2 text-sm outline-none aria-selected:bg-primary/15 aria-selected:text-foreground data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50',
      className
    )}
    {...props}
  />
))
CommandItem.displayName = CommandPrimitive.Item.displayName

export const CommandShortcut = ({ className, ...props }) => (
  <span className={cn('ml-auto text-xs tracking-widest text-muted-foreground', className)} {...props} />
)
