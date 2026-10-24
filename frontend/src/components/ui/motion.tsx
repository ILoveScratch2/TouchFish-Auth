import { forwardRef } from "react";
import type { ReactNode } from "react";
import {
  motion,
  useReducedMotion,
  type HTMLMotionProps,
  type Transition,
  type Variants,
} from "framer-motion";

export const springs = {
  snappy: { type: "spring", stiffness: 500, damping: 30 },
  smooth: { type: "spring", stiffness: 300, damping: 30 },
  bouncy: { type: "spring", stiffness: 400, damping: 15 },
  gentle: { type: "spring", stiffness: 200, damping: 24 },
  exit: { type: "spring", stiffness: 300, damping: 35 },
} as const;

export const easings = {
  easeOutExpo: [0.16, 1, 0.3, 1],
  easeOutQuart: [0.25, 1, 0.5, 1],
  easeOutBack: [0.34, 1.56, 0.64, 1],
  easeInOutQuart: [0.76, 0, 0.24, 1],
} as const;

export const transitions = {
  fast: { duration: 0.15, ease: easings.easeOutExpo },
  normal: { duration: 0.25, ease: easings.easeOutExpo },
  slow: { duration: 0.4, ease: easings.easeOutExpo },
} as const;

export const pageVariants: Variants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -12 },
};

export const authContainerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1, delayChildren: 0.2 },
  },
};

export const authItemVariants: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
};

export const listContainerVariants: Variants = {
  initial: {},
  animate: { transition: { staggerChildren: 0.05, delayChildren: 0.1 } },
};

export const listItemVariants: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
};

const reducedTransition: Transition = { duration: 0 };

interface PageWrapperProps {
  children: ReactNode;
  className?: string;
}

export const PageWrapper = forwardRef<HTMLDivElement, PageWrapperProps>(
  ({ children, className }, ref) => {
    const reduced = useReducedMotion();
    return (
      <motion.div
        ref={ref}
        initial={reduced ? { opacity: 0 } : "initial"}
        animate="animate"
        variants={
          reduced
            ? { initial: { opacity: 0 }, animate: { opacity: 1 } }
            : pageVariants
        }
        transition={reduced ? reducedTransition : springs.smooth}
        className={className}
      >
        {children}
      </motion.div>
    );
  },
);
PageWrapper.displayName = "PageWrapper";

type AnimatedButtonProps = HTMLMotionProps<"div">;

export const AnimatedButton = forwardRef<HTMLDivElement, AnimatedButtonProps>(
  ({ children, className, ...rest }, ref) => {
    const reduced = useReducedMotion();
    return (
      <motion.div
        ref={ref}
        whileHover={reduced ? undefined : { scale: 1.02 }}
        whileTap={reduced ? undefined : { scale: 0.98 }}
        transition={reduced ? reducedTransition : springs.snappy}
        className={className}
        {...rest}
      >
        {children}
      </motion.div>
    );
  },
);
AnimatedButton.displayName = "AnimatedButton";

export { motion };
