import { motion } from 'framer-motion';

const variants = {
  initial: { opacity: 0, y: 8 },
  enter:   { opacity: 1, y: 0, transition: { type: 'spring', damping: 28, stiffness: 280, mass: 0.7 } },
  exit:    { opacity: 0, y: -4, transition: { duration: 0.14, ease: [0.4, 0, 1, 1] } },
};

/**
 * Page-shell animation. Wrap any screen's root element with this and the
 * children will fade + slide 8px upward with an iOS-style spring as they
 * mount, and fade + slide 4px upward as they unmount.
 *
 * Pairs with <AnimatePresence mode="wait"> at the call site to get
 * sequential screen transitions.
 */
export default function PageShell({ children, className, style, as = 'div' }) {
  const MotionTag = motion[as] || motion.div;
  return (
    <MotionTag
      className={className}
      style={style}
      variants={variants}
      initial="initial"
      animate="enter"
      exit="exit"
    >
      {children}
    </MotionTag>
  );
}
