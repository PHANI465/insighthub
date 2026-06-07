interface Props {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}

const sizes = {
  sm: 'h-4 w-4 border-2',
  md: 'h-8 w-8 border-2',
  lg: 'h-12 w-12 border-4',
}

export default function LoadingSpinner({ size = 'md', label }: Props) {
  return (
    <div className="flex flex-col items-center gap-3">
      <div
        className={`${sizes[size]} animate-spin rounded-full border-blue-500 border-t-transparent`}
        role="status"
        aria-label={label ?? 'Loading'}
      />
      {label && <p className="text-sm text-gray-500">{label}</p>}
    </div>
  )
}
