"use client"

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { useReducedMotion } from "@/lib/use-reduced-motion"

const badgeVariants = cva(
  [
    // Base styles
    "inline-flex items-center justify-center gap-1.5",
    "text-xs font-medium",
    "whitespace-nowrap",
    "border",
  ],
  {
    variants: {
      variant: {
        default: "bg-primary/10",
        outline: "bg-transparent border-2",
        filled: "bg-primary text-primary-foreground",
      },
      status: {
        default: "text-primary border-primary/30",
        success: "text-green-500 border-green-500/30",
        warning: "text-yellow-500 border-yellow-500/30",
        error: "text-red-500 border-red-500/30",
        info: "text-blue-500 border-blue-500/30",
      },
      size: {
        default: "h-6 px-3 py-1",
        sm: "h-5 px-2 py-0.5 text-[10px]",
        lg: "h-8 px-4 py-1.5 text-sm",
      },
      intensity: {
        subtle: [
          // Minimal - rounded, no glow
          "rounded-full",
        ],
        medium: [
          // Noticeable - small clip, faint glow, mono font
          "[clip-path:polygon(0_4px,4px_0,100%_0,100%_calc(100%-4px),calc(100%-4px)_100%,0_100%)]",
          "shadow-[0_0_8px_currentColor]",
          "font-[family-name:var(--font-jetbrains)]",
        ],
        full: [
          // Complete cyberpunk - clip corners, intense glow, uppercase
          "[clip-path:polygon(0_4px,4px_0,100%_0,100%_calc(100%-4px),calc(100%-4px)_100%,0_100%)]",
          "shadow-[0_0_12px_currentColor,inset_0_0_6px_currentColor]",
          "font-[family-name:var(--font-orbitron)] uppercase tracking-wider",
        ],
      },
    },
    compoundVariants: [
      // Filled variant overrides
      {
        variant: "filled",
        status: "default",
        className: "bg-primary text-primary-foreground border-primary",
      },
      {
        variant: "filled",
        status: "success",
        className: "bg-green-500 text-white border-green-500",
      },
      {
        variant: "filled",
        status: "warning",
        className: "bg-yellow-500 text-black border-yellow-500",
      },
      {
        variant: "filled",
        status: "error",
        className: "bg-red-500 text-white border-red-500",
      },
      {
        variant: "filled",
        status: "info",
        className: "bg-blue-500 text-white border-blue-500",
      },
      // Outline variant with status colors
      {
        variant: "outline",
        status: "success",
        className: "border-green-500",
      },
      {
        variant: "outline",
        status: "warning",
        className: "border-yellow-500",
      },
      {
        variant: "outline",
        status: "error",
        className: "border-red-500",
      },
      {
        variant: "outline",
        status: "info",
        className: "border-blue-500",
      },
    ],
    defaultVariants: {
      variant: "default",
      status: "default",
      size: "default",
      intensity: "subtle",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  icon?: React.ReactNode
  dot?: boolean
  animated?: boolean
}

const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  (
    {
      className,
      variant,
      status,
      size,
      intensity = "subtle",
      icon,
      dot = false,
      animated = true,
      children,
      ...props
    },
    ref
  ) => {
    const prefersReducedMotion = useReducedMotion()
    const shouldAnimate = animated && !prefersReducedMotion

    // Dot pulsing only at full intensity
    const showPulsingDot = dot && intensity === "full" && shouldAnimate

    return (
      <span
        ref={ref}
        data-slot="badge"
        className={cn(
          badgeVariants({ variant, status, size, intensity }),
          shouldAnimate && "transition-all duration-300 ease-out",
          !shouldAnimate && "transition-none",
          className
        )}
        {...props}
      >
        {/* Status dot indicator */}
        {dot && (
          <span
            className={cn(
              "size-1.5 rounded-full",
              showPulsingDot && "animate-[cyber-glow-pulse_1.5s_ease-in-out_infinite]",
              status === "success" && "bg-green-500",
              status === "warning" && "bg-yellow-500",
              status === "error" && "bg-red-500",
              status === "info" && "bg-blue-500",
              status === "default" && "bg-primary"
            )}
            aria-hidden="true"
          />
        )}

        {/* Icon */}
        {icon && (
          <span className="flex size-3.5 items-center justify-center">
            {icon}
          </span>
        )}

        {/* Content */}
        {children}
      </span>
    )
  }
)
Badge.displayName = "Badge"

/* ========================================
   Status Badge Preset
   ======================================== */

const StatusBadge = React.forwardRef<
  HTMLSpanElement,
  Omit<BadgeProps, "dot"> & {
    online?: boolean
  }
>(({ online = true, status, intensity, animated, children, ...props }, ref) => (
  <Badge
    ref={ref}
    variant="default"
    status={status || (online ? "success" : "error")}
    intensity={intensity}
    animated={animated}
    dot
    {...props}
  >
    {children || (online ? "Online" : "Offline")}
  </Badge>
))
StatusBadge.displayName = "StatusBadge"

export { Badge, StatusBadge, badgeVariants }
