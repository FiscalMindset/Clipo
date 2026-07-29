import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence, useDragControls } from 'framer-motion';

/**
 * Bottom-sheet wrapper for modals on phone.
 *
 * - On phones (≤768px), the sheet slides up from the bottom edge, has rounded
 *   top corners, a grabber, and drag-to-dismiss.
 * - On larger screens it falls back to the centered modal style.
 *
 * Children render in the sheet body. The backdrop is dismissable via tap.
 * Pass `onClose` to control close; pass `onOpenChange` for open state.
 */
export default function BottomSheet({
  open,
  onClose,
  children,
  title,
  initialSnap = 0.92,
  ariaLabel,
}) {
  const sheetRef = useRef(null);
  const [isMobile, setIsMobile] = useState(false);
  const dragControls = useDragControls();
  const [dragY, setDragY] = useState(0);

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener('change', update);
    return () => mq.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="bottom-sheet-root"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) onClose?.();
          }}
        >
          {isMobile ? (
            <motion.div
              ref={sheetRef}
              className="bottom-sheet"
              role="dialog"
              aria-modal="true"
              aria-label={ariaLabel || title}
              initial={{ y: '100%' }}
              animate={{ y: dragY }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', damping: 32, stiffness: 360, mass: 0.8 }}
              drag="y"
              dragControls={dragControls}
              dragListener={false}
              dragConstraints={{ top: 0, bottom: 0 }}
              dragElastic={{ top: 0, bottom: 0.6 }}
              onDrag={(_, info) => setDragY(Math.max(0, info.offset.y))}
              onDragEnd={(_, info) => {
                if (info.offset.y > 120 || info.velocity.y > 600) {
                  onClose?.();
                }
                setDragY(0);
              }}
            >
              <div
                className="bottom-sheet-grabber"
                onPointerDown={(e) => dragControls.start(e)}
                role="button"
                aria-label="Drag to close"
              >
                <span />
              </div>
              <div className="bottom-sheet-body">
                {children}
              </div>
            </motion.div>
          ) : (
            <motion.div
              className="bottom-sheet-modal"
              role="dialog"
              aria-modal="true"
              aria-label={ariaLabel || title}
              initial={{ opacity: 0, scale: 0.96, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: 12 }}
              transition={{ duration: 0.2, ease: [0.2, 0.9, 0.3, 1.2] }}
              onMouseDown={(e) => {
                if (e.target === e.currentTarget) onClose?.();
              }}
            >
              {children}
            </motion.div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
