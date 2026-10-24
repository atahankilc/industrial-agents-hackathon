// GLSL for the building cloud. Everything animates on the GPU from uniforms and a per-space state texture,
// so the CPU only eases a few hundred numbers per frame. Monochrome: meaning is carried by alpha, size and
// motion, never by hue (docs/product/visualization.md, D-011).

export const MAX_FLOORS = 32

export const cloudVertex = /* glsl */ `
  uniform float uTime, uEmerge, uScanY, uDensity, uExplode, uSize, uScale, uAnyHighlight, uAnyRoute;
  uniform float uFloorOn[${MAX_FLOORS}];
  uniform sampler2D uSpaceState; // per space: r highlight, g lost access, b closed, a on route
  attribute vec3 aScatter;
  attribute float aKind, aFloor, aSpace, aReveal;
  varying float vAlpha;
  varying float vGlow;

  float hash(float n) { return fract(sin(n) * 43758.5453); }

  void main() {
    vec4 state = aSpace >= 0.0 ? texelFetch(uSpaceState, ivec2(int(aSpace), 0), 0) : vec4(0.0);
    float lit = state.r, lost = state.g, closed = state.b, onRoute = state.a;
    float floorOn = uFloorOn[int(aFloor)];

    // Emergence: low-reveal points arrive first (outline), the rest fill in; exponential ease-out.
    float t = clamp(uEmerge * 1.7 - aReveal * 0.7, 0.0, 1.0);
    float arrive = t >= 1.0 ? 1.0 : 1.0 - pow(2.0, -10.0 * t);

    vec3 home = position + vec3(0.0, aFloor * uExplode, 0.0);
    home.y += sin(uTime * 0.55 + aReveal * 31.0) * 0.012;                         // idle breathing
    home.y += lit * (0.10 + 0.06 * sin(uTime * 2.2 + aReveal * 17.0));              // highlighted rooms float
    home += lost * vec3(sin(aReveal * 91.0) * 0.35, -0.5 - aReveal * 0.9, cos(aReveal * 57.0) * 0.35); // sink
    vec3 p = mix(aScatter, home, arrive);

    // Kind → base alpha / size: walls 0, floors 1, doors 2, stairs+lifts 3, assets 4.
    float alpha = aKind == 0.0 ? 0.78 : aKind == 1.0 ? 0.2 : aKind == 2.0 ? 1.0 : aKind == 3.0 ? 0.62 : 0.55;
    float size = aKind == 1.0 ? 0.7 : aKind == 2.0 ? 1.3 : aKind == 4.0 ? 0.85 : 1.0;
    if (aKind == 3.0) alpha *= 0.85 + 0.15 * sin(uTime * 1.4 + aFloor);                // cores pulse softly

    float scan = exp(-pow((home.y - uScanY) * 1.4, 2.0)) * step(uEmerge, 0.999);       // scan plane glow
    float flicker = step(0.45, hash(floor(uTime * 14.0) + aReveal * 97.0));

    alpha = mix(alpha, alpha * 0.16, uAnyHighlight * (1.0 - lit)) + lit * 0.35;
    alpha *= 1.0 - lost * 0.88;
    alpha *= 1.0 - closed * (0.35 + 0.55 * flicker);
    // An active route pulls focus: rooms it passes stay bright, the rest of the building steps back.
    alpha *= mix(1.0, 0.28 + 0.72 * onRoute, uAnyRoute * (1.0 - uAnyHighlight));
    alpha = clamp(alpha + scan * 0.9, 0.0, 1.0);

    float visible = step(aReveal, uDensity) * floorOn;
    vAlpha = alpha * (0.2 + 0.8 * arrive) * visible;
    vGlow = scan + lit * 0.5;

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    float px = uSize * size * (1.0 + lit * 0.7 + scan * 0.8) * 0.1 * uScale / -mv.z;
    gl_PointSize = visible > 0.0 ? max(1.25, px) : 0.0;
    gl_Position = projectionMatrix * mv;
  }
`

export const cloudFragment = /* glsl */ `
  uniform vec3 uInk;
  uniform float uDark;
  varying float vAlpha;
  varying float vGlow;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    if (d > 0.5) discard;
    // Dark: soft glowing dots, additive. Light: crisp ink dots, normal blending.
    float shape = uDark > 0.5 ? smoothstep(0.5, 0.0, d) : smoothstep(0.5, 0.32, d);
    float a = vAlpha * shape * (1.0 + vGlow * 0.4);
    gl_FragColor = uDark > 0.5 ? vec4(uInk * a, a) : vec4(uInk, a * 0.9);
  }
`

export const routeVertex = /* glsl */ `
  uniform float uScale, uSize;
  attribute float aHead; // 1 at the comet head, fading to 0 along its tail
  varying float vHead;
  void main() {
    vHead = aHead;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = max(1.5, uSize * (0.35 + 0.9 * aHead) * uScale / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`

export const routeFragment = /* glsl */ `
  uniform vec3 uInk;
  uniform float uDark, uOpacity;
  varying float vHead;
  void main() {
    float d = length(gl_PointCoord - 0.5);
    if (d > 0.5) discard;
    float a = smoothstep(0.5, 0.1, d) * (0.25 + 0.75 * vHead) * uOpacity;
    gl_FragColor = uDark > 0.5 ? vec4(uInk * a, a) : vec4(uInk, a);
  }
`
