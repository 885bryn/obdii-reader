import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import { useReducedMotion } from "@/lib/use-reduced-motion"

const cardVariants = cva(
  [
    // Base styles (always applied)
    "relative overflow-hidden",
    "flex flex-col",
    "bg-card text-card-foreground",
    "border",
  ],
  {
    variants: {
      variant: {
        default: "bg-gradient-to-br from-card via-card to-muted/20",
        holographic: "bg-gradient-to-br from-card via-muted/10 to-card",
        terminal: "bg-background font-[family-name:var(--font-jetbrains)]",
      },
      intensity: {
        subtle: [
          // Minimal - rounded corners, faint glow
          "rounded-lg",
          "border-border",
          "shadow-sm",
        ],
        medium: [
          // Noticeable - small clip, moderate glow
          "[clip-path:polygon(0_8px,8px_0,100%_0,100%_calc(100%-8px),calc(100%-8px)_100%,0_100%)]",
          "border-primary/20",
          "shadow-[0_0_15px_var(--cyber-glow)]",
        ],
        full: [
          // Complete cyberpunk - large clip, intense glow
          "[clip-path:polygon(0_12px,12px_0,100%_0,100%_calc(100%-12px),calc(100%-12px)_100%,0_100%)]",
          "border-primary/30",
          "shadow-[0_0_20px_var(--cyber-glow)]",
        ],
      },
      glowColor: {
        primary: "",
        cyan: "border-cyan-500/30 shadow-[0_0_20px_rgba(0,255,255,0.3)]",
        magenta: "border-pink-500/30 shadow-[0_0_20px_rgba(255,0,255,0.3)]",
        green: "border-green-500/30 shadow-[0_0_20px_rgba(0,255,100,0.3)]",
        orange: "border-orange-500/30 shadow-[0_0_20px_rgba(255,165,0,0.3)]",
      },
    },
    compoundVariants: [
      // Hover effects per intensity
      {
        intensity: "medium",
        className: "hover:shadow-[0_0_25px_var(--cyber-glow)] hover:border-primary/40",
      },
      {
        intensity: "full",
        className: "hover:shadow-[0_0_30px_var(--cyber-glow)] hover:border-primary/50",
      },
    ],
    defaultVariants: {
      variant: "default",
      intensity: "subtle",
      glowColor: "primary",
    },
  }
)

// Create context to pass intensity and animated to sub-components
interface CardContextValue {
  intensity: "subtle" | "medium" | "full"
  animated: boolean
  shouldAnimate: boolean
}

const CardContext = React.createContext<CardContextValue>({
  intensity: "subtle",
  animated: true,
  shouldAnimate: true,
})

export interface CardProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {
  animated?: boolean
}

const Card = React.forwardRef<HTMLDivElement, CardProps>(
  (
    {
      className,
      variant,
      intensity = "subtle",
      glowColor,
      animated = true,
      children,
      ...props
    },
    ref
  ) => {
    const prefersReducedMotion = useReducedMotion()
    const shouldAnimate = animated && !prefersReducedMotion

    // Determine features based on intensity
    const showScanLines = intensity === "full" && shouldAnimate
    const showCornerAccents = intensity === "medium" || intensity === "full"

    return (
      <CardContext.Provider value={{ intensity: intensity ?? "subtle", animated, shouldAnimate }}>
        <div
          ref={ref}
          data-slot="card"
          className={cn(
            cardVariants({ variant, intensity, glowColor }),
            shouldAnimate && "transition-all duration-300 ease-out",
            !shouldAnimate && "transition-none",
            className
          )}
          {...props}
        >
          {/* Scan line overlay (full intensity + animated only) */}
          {showScanLines && (
            <div
              className="pointer-events-none absolute inset-0 z-10"
              aria-hidden="true"
            >
              {/* Static scan lines */}
              <div
                className="absolute inset-0 opacity-[0.03]"
                style={{
                  backgroundImage: `repeating-linear-gradient(
                    0deg,
                    transparent,
                    transparent 2px,
                    var(--cyber-primary) 2px,
                    var(--cyber-primary) 4px
                  )`,
                }}
              />
              {/* Animated scan line */}
              <div
                className="absolute inset-0 animate-[cyber-scanline_4s_linear_infinite] bg-gradient-to-b from-transparent via-primary/10 to-transparent"
                style={{ height: "30%" }}
              />
            </div>
          )}

          {/* Holographic shimmer overlay (holographic variant + full intensity + animated) */}
          {variant === "holographic" && intensity === "full" && shouldAnimate && (
            <div
              className="pointer-events-none absolute inset-0 z-10 animate-[cyber-holographic_3s_ease_infinite] opacity-20"
              style={{
                backgroundImage: `linear-gradient(
                  45deg,
                  transparent 30%,
                  var(--cyber-primary) 40%,
                  var(--cyber-secondary) 50%,
                  var(--cyber-primary) 60%,
                  transparent 70%
                )`,
                backgroundSize: "200% 200%",
              }}
              aria-hidden="true"
            />
          )}

          {/* Terminal CRT effect (terminal variant + full intensity + animated) */}
          {variant === "terminal" && intensity === "full" && shouldAnimate && (
            <div
              className="pointer-events-none absolute inset-0 z-10 animate-[cyber-flicker_4s_ease-in-out_infinite]"
              style={{
                background: `radial-gradient(
                  ellipse at center,
                  transparent 0%,
                  var(--background) 100%
                )`,
                opacity: 0.3,
              }}
              aria-hidden="true"
            />
          )}

          {/* Corner accent decorations (medium and full intensity) */}
          {showCornerAccents && (
            <>
              <span
                className={cn(
                  "pointer-events-none absolute border-l-2 border-t-2 border-primary/60",
                  intensity === "medium" ? "left-0.5 top-0.5 h-3 w-3" : "left-1 top-1 h-4 w-4"
                )}
                aria-hidden="true"
              />
              <span
                className={cn(
                  "pointer-events-none absolute border-r-2 border-t-2 border-primary/60",
                  intensity === "medium" ? "right-0.5 top-0.5 h-3 w-3" : "right-1 top-1 h-4 w-4"
                )}
                aria-hidden="true"
              />
              <span
                className={cn(
                  "pointer-events-none absolute border-b-2 border-l-2 border-primary/60",
                  intensity === "medium" ? "bottom-0.5 left-0.5 h-3 w-3" : "bottom-1 left-1 h-4 w-4"
                )}
                aria-hidden="true"
              />
              <span
                className={cn(
                  "pointer-events-none absolute border-b-2 border-r-2 border-primary/60",
                  intensity === "medium" ? "bottom-0.5 right-0.5 h-3 w-3" : "bottom-1 right-1 h-4 w-4"
                )}
                aria-hidden="true"
              />
            </>
          )}

          {/* Content wrapper */}
          <div className="relative z-20">{children}</div>
        </div>
      </CardContext.Provider>
    )
  }
)
Card.displayName = "Card"

/* ========================================
   Sub-components
   ======================================== */

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => {
  const { intensity } = React.useContext(CardContext)

  return (
    <div
      ref={ref}
      data-slot="card-header"
      className={cn(
        "flex flex-col gap-1.5 px-6 pt-6",
        intensity !== "subtle" && "border-b border-primary/10 pb-4",
        className
      )}
      {...props}
    />
  )
})
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => {
  const { intensity } = React.useContext(CardContext)

  return (
    <h3
      ref={ref}
      data-slot="card-title"
      className={cn(
        "text-lg font-semibold leading-none tracking-tight",
        intensity === "medium" && "font-[family-name:var(--font-jetbrains)] text-primary",
        intensity === "full" && [
          "font-[family-name:var(--font-orbitron)] uppercase tracking-wider",
          "text-primary cyber-text-glow",
        ],
        className
      )}
      {...props}
    />
  )
})
CardTitle.displayName = "CardTitle"

const CardDescription = React.forwardRef<
  HTMLParagraphElement,
  React.HTMLAttributes<HTMLParagraphElement>
>(({ className, ...props }, ref) => {
  const { intensity } = React.useContext(CardContext)

  return (
    <p
      ref={ref}
      data-slot="card-description"
      className={cn(
        "text-sm text-muted-foreground",
        intensity !== "subtle" && "font-[family-name:var(--font-jetbrains)]",
        className
      )}
      {...props}
    />
  )
})
CardDescription.displayName = "CardDescription"

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    data-slot="card-content"
    className={cn("flex-1 px-6 py-4", className)}
    {...props}
  />
))
CardContent.displayName = "CardContent"

const CardFooter = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => {
  const { intensity } = React.useContext(CardContext)

  return (
    <div
      ref={ref}
      data-slot="card-footer"
      className={cn(
        "flex items-center gap-4 px-6 pb-6 pt-2",
        intensity !== "subtle" && "border-t border-primary/10",
        className
      )}
      {...props}
    />
  )
})
CardFooter.displayName = "CardFooter"

export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  cardVariants,
}
