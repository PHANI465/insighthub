type Variant = 'blue' | 'green' | 'amber' | 'red' | 'gray' | 'violet'

interface Props {
  label: string
  variant?: Variant
}

const variants: Record<Variant, string> = {
  blue:   'bg-blue-100 text-blue-700',
  green:  'bg-emerald-100 text-emerald-700',
  amber:  'bg-amber-100 text-amber-700',
  red:    'bg-red-100 text-red-700',
  gray:   'bg-gray-100 text-gray-600',
  violet: 'bg-violet-100 text-violet-700',
}

export default function Badge({ label, variant = 'gray' }: Props) {
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${variants[variant]}`}
    >
      {label}
    </span>
  )
}
