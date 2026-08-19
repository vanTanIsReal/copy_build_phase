import { Bot, CalendarPlus, ClipboardList, LayoutDashboard, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandShortcut } from '../ui/command'

// Global Cmd+K / Ctrl+K power-user palette (design brief Phase 2). Mounted once in AppLayout so
// it's available from any page without each page wiring its own listener. Actions below are
// mocked (console.info) where there's no real endpoint yet - same "demo, not live" honesty as
// WorkspaceBriefsPage - "Go to QA Workspace" is the one real action, it navigates to the actual
// multi-agent UI shell route.
export default function CommandPalette() {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    const onKeyDown = (event) => {
      const isCombo = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k'
      if (!isCombo) return
      event.preventDefault()
      setOpen((prev) => !prev)
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  const run = (fn) => {
    setOpen(false)
    fn()
  }

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Gõ một lệnh hoặc tìm kiếm..." />
      <CommandList>
        <CommandEmpty>Không tìm thấy kết quả.</CommandEmpty>
        <CommandGroup heading="AI Agents">
          <CommandItem onSelect={() => run(() => console.info('[CommandPalette] Ask Executive Agent - not wired to a live endpoint yet'))}>
            <Bot className="text-primary" />
            <span>Ask Executive Agent</span>
            <CommandShortcut>Demo</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => run(() => navigate('/workspace-briefs'))}>
            <ShieldCheck className="text-primary" />
            <span>Go to QA Workspace</span>
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading="Actions">
          <CommandItem onSelect={() => run(() => console.info('[CommandPalette] Create new meeting - not wired to a live endpoint yet'))}>
            <CalendarPlus className="text-primary" />
            <span>Create new meeting</span>
            <CommandShortcut>Demo</CommandShortcut>
          </CommandItem>
          <CommandItem onSelect={() => run(() => navigate('/tasks/inbox'))}>
            <ClipboardList className="text-primary" />
            <span>Go to Task Inbox</span>
          </CommandItem>
          <CommandItem onSelect={() => run(() => navigate('/workspace-briefs'))}>
            <LayoutDashboard className="text-primary" />
            <span>Go to Workspace Briefs</span>
          </CommandItem>
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
