/**
 * Adapted React Bits CountUp effect for data-rich dashboard KPIs.
 * React Bits original: https://github.com/DavidHDev/react-bits/blob/main/src/content/TextAnimations/CountUp/CountUp.jsx
 * Uses the same Motion primitives (useMotionValue, useSpring, useInView),
 * with decimal formatting, prefix/suffix, updates, and reduced-motion support.
 */
import { useInView, useMotionValue, useSpring } from 'motion/react';
import { useEffect, useRef, useState } from 'react';

export default function CountUp({ value, decimals = 0, prefix = '', suffix = '' }) {
  const ref = useRef(null);
  const target = Number(value) || 0;
  const [shown, setShown] = useState(0);
  const motionValue = useMotionValue(0);
  const springValue = useSpring(motionValue, { stiffness: 105, damping: 24 });
  const visible = useInView(ref, { once: true, amount: 0.1 });

  useEffect(() => {
    if (!visible) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      springValue.jump(target);
      setShown(target);
    } else {
      motionValue.set(target);
    }
  }, [visible, target, motionValue, springValue]);

  useEffect(() => springValue.on('change', setShown), [springValue]);

  return <span ref={ref} className="count-num" aria-label={`${prefix}${target.toFixed(decimals)}${suffix}`}>
    {prefix}{shown.toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })}{suffix}
  </span>;
}
