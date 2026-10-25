// Reduced motion: the app always starts with full motion, whatever the OS "reduce motion" setting says (the CSS
// has no prefers-reduced-motion blocks either). The motion code keeps its calm branches behind this one switch.
export const reducedMotion = () => false
