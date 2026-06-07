import { AlertCircle, X } from 'lucide-react'

interface Props {
  message: string
  onDismiss?: () => void
}

export default function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
      <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-500" />
      <p className="flex-1 text-sm text-red-700">{message}</p>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="shrink-0 text-red-300 hover:text-red-500"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  )
}
