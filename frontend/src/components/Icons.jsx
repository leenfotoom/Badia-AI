import React from 'react'

const paths = {
  map: <path d="m4 6 5-2 6 2 5-2v14l-5 2-6-2-5 2V6Zm5-2v14m6-12v14" />,
  science: <path d="M9 3h6m-5 0v5l-5 9a2.6 2.6 0 0 0 2.3 4h9.4a2.6 2.6 0 0 0 2.3-4l-5-9V3m-6.4 11h8.8" />,
  home: <path d="m3 11 9-8 9 8m-16 0v10h14V11M9 21v-6h6v6" />,
  arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
  calendar: <path d="M7 3v3m10-3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z" />,
  satellite: <path d="m8 8 8 8m-9-3-4 4 4 4 4-4m6-6 4-4-4-4-4 4m-2 3-1.5 1.5m3 1.5-1.5 1.5M4 4l4 1-3 3-1-4Zm16 16-4-1 3-3 1 4Z" />,
  layers: <path d="m3 8 9-5 9 5-9 5-9-5Zm0 4 9 5 9-5m-18 4 9 5 9-5" />,
  location: <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Zm-8 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" />,
  chart: <path d="M4 20V10m6 10V4m6 16v-7m4 7H2" />,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10h.01" /></>,
  close: <path d="m6 6 12 12M18 6 6 18" />,
  chevron: <path d="m9 18 6-6-6-6" />,
  quality: <path d="m12 3 7 3v5c0 4.8-2.9 8.1-7 10-4.1-1.9-7-5.2-7-10V6l7-3Zm-3 9 2 2 4-4" />,
  offline: <path d="M3 9a15 15 0 0 1 18 0M6 13a10 10 0 0 1 12 0m-9 4a5 5 0 0 1 6 0m-3 4h.01M3 3l18 18" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  language: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.4 2.5 3.6 5.5 3.6 9S14.4 18.5 12 21m0-18C9.6 5.5 8.4 8.5 8.4 12s1.2 6.5 3.6 9" /></>,
  water: <path d="M12 3s6 6.3 6 11a6 6 0 0 1-12 0c0-4.7 6-11 6-11Zm-3 12c.5 1.5 1.6 2.3 3 2.5" />,
  field: <path d="M3 18c4-4 8-4 12 0M2 13c5-4 10-4 15 0m-9-8v6m0-3c-2-2-4-2-5-1m5 1c2-2 4-2 5-1m6 3v11m-3-8h6" />,
  check: <path d="m5 12 4 4L19 6" />,
  alert: <><path d="M12 3 2.7 20h18.6L12 3Z" /><path d="M12 9v5m0 3h.01" /></>,
}

export default function Icon({ name, size = 20, className = '' }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.7"
    >
      {paths[name]}
    </svg>
  )
}

export function BrandMark({ compact = false }) {
  return (
    <img
      className={`brand-logo ${compact ? 'brand-logo--compact' : ''}`}
      src="/logo-full-light.png"
      alt=""
      width="173"
      height="48"
      decoding="async"
      draggable="false"
    />
  )
}
