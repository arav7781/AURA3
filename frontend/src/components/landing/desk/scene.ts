import * as THREE from 'three'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'

// The hero's desk: an evergreen leather blotter with a gold-tooled border on a dark lacquered desk, under a
// lamp, with three printed pages of the KrishiMitra AI deck and a few AuraCoins. Page 4 sits on top; TitanOCR's line boxes, the cited claim and
// the figure being checked are drawn onto it by one shader, so they bend with the paper. The camera moves
// between four shots, one per step, and the page is always framed inside `slot`.

export type Box = [number, number, number, number] // x0, y0, x1, y1 as fractions of the page, y down

export interface DeskFrame {
  /** How far down the page the scan has reached, 0..1. */
  reveal: number
  /** Page point (fractions, y down) to host pixels. */
  project: (u: number, v: number) => [number, number]
  width: number
  height: number
}

export interface DeskOptions {
  canvas: HTMLCanvasElement
  host: HTMLElement
  slot: HTMLElement
  pages: { top: string; under: [string, string] }
  aspect: number
  lines: Box[]
  cited: number[]
  /** The figure checked on step 3, as a box on the page. */
  figure: Box
  reduced: boolean
  /** Resolution of the overlay masks, as a multiple of 1754 px wide (2 on large screens, for crisp boxes). */
  detail: number
  /** Seconds after the pages are loaded before the scan starts: the entrance plays first. */
  scanDelay: number
  onFrame?: (frame: DeskFrame) => void
}

export interface Desk {
  ready: Promise<void>
  setStep: (step: number) => void
  dispose: () => void
}

const PAGE_W = 3.2
const FOV = 30
const BASE_ELEV = 60
const BASE_AZIM = -5
const SCAN_SECONDS = 2.4
const SCAN_END = 1.06

// One camera shot per step: where on the page to look, how close, and a small orbit.
const SHOTS = [
  { u: 0.56, v: 0.52, zoom: 1, azim: 0, elev: 0 },
  { u: 0.44, v: 0.37, zoom: 1.3, azim: -4, elev: 3 },
  { u: 0.42, v: 0.32, zoom: 1.6, azim: 5, elev: 5 },
  { u: 0.66, v: 0.58, zoom: 0.94, azim: 9, elev: -3 },
]
// Overlay strength per step: every line, the cited claim, the checked figure.
const LAYERS = [
  [1, 0, 0],
  [0.22, 1, 0],
  [0.1, 0.4, 1],
  [0.28, 0.65, 0.75],
]

const JADE = '#1f9670'
const JADE_DEEP = '#0d6b4f'
const GOLD = '#e7a73a'
const BEAM = '#8af5cc'
const BLOTTER = { x0: -2.45, x1: 2.95, z0: -1.9, z1: 2.3, h: 0.035 }

function rng(seed: number) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function canvas(w: number, h: number) {
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  return [c, c.getContext('2d')!] as const
}

/** A tiling pebble-grain height map; brighter = raised. */
function leatherGrain(size = 512) {
  const [c, g] = canvas(size, size)
  const rand = rng(11)
  g.fillStyle = '#3a3a3a'
  g.fillRect(0, 0, size, size)
  for (let i = 0; i < 5200; i++) {
    const x = rand() * size
    const y = rand() * size
    const r = 2.5 + rand() * 4
    const v = 110 + Math.round(rand() * 60)
    for (const dx of [-size, 0, size]) {
      for (const dy of [-size, 0, size]) {
        const cx = x + dx
        const cy = y + dy
        if (cx < -r || cy < -r || cx > size + r || cy > size + r) continue
        const grad = g.createRadialGradient(cx, cy, 0, cx, cy, r)
        grad.addColorStop(0, `rgb(${v},${v},${v})`)
        grad.addColorStop(0.65, `rgba(${v},${v},${v},0.85)`)
        grad.addColorStop(1, 'rgba(58,58,58,0)')
        g.fillStyle = grad
        g.beginPath()
        g.arc(cx, cy, r, 0, Math.PI * 2)
        g.fill()
      }
    }
  }
  const img = g.getImageData(0, 0, size, size)
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (rand() - 0.5) * 18
    img.data[i] = img.data[i + 1] = img.data[i + 2] = Math.max(0, Math.min(255, img.data[i] + n))
  }
  g.putImageData(img, 0, 0)
  return c
}

/** Leather colour: evergreen, darker in the creases of the grain. */
function leatherColour(grain: HTMLCanvasElement) {
  const [c, g] = canvas(grain.width, grain.height)
  g.fillStyle = '#0b3a2f'
  g.fillRect(0, 0, c.width, c.height)
  g.globalCompositeOperation = 'multiply'
  g.globalAlpha = 0.4
  g.drawImage(grain, 0, 0)
  g.globalCompositeOperation = 'source-over'
  g.globalAlpha = 1
  return c
}

/** The AuraCoin face as a height map: rim, legend and the three-arc mark. */
function coinFace(size = 512) {
  const [c, g] = canvas(size, size)
  const m = size / 2
  g.fillStyle = '#6a6a6a'
  g.fillRect(0, 0, size, size)
  g.strokeStyle = '#e8e8e8'
  g.lineWidth = size * 0.05
  g.beginPath()
  g.arc(m, m, size * 0.465, 0, Math.PI * 2)
  g.stroke()
  g.lineWidth = size * 0.012
  g.beginPath()
  g.arc(m, m, size * 0.36, 0, Math.PI * 2)
  g.stroke()
  // Legend around the rim
  g.fillStyle = '#d8d8d8'
  g.font = `600 ${Math.round(size * 0.052)}px Arial, sans-serif`
  g.textAlign = 'center'
  g.textBaseline = 'middle'
  const legend = 'AURACOIN · ONE AC · AURA3 · '
  const step = (Math.PI * 2) / legend.length
  for (let i = 0; i < legend.length; i++) {
    const a = -Math.PI / 2 + i * step
    g.save()
    g.translate(m + Math.cos(a) * size * 0.405, m + Math.sin(a) * size * 0.405)
    g.rotate(a + Math.PI / 2)
    g.fillText(legend[i], 0, 0)
    g.restore()
  }
  // The brand mark: three arcs around a core (same geometry as the navbar logo, 24-unit box)
  const k = (size * 0.5) / 24
  g.save()
  g.translate(m - 12 * k, m - 12 * k)
  g.scale(k, k)
  g.strokeStyle = '#f4f4f4'
  g.lineCap = 'round'
  g.lineWidth = 2.4
  for (const d of ['M13.56 3.14A9 9 0 0 1 20.46 15.08', 'M18.89 17.79A9 9 0 0 1 5.11 17.79', 'M3.54 15.08A9 9 0 0 1 10.44 3.14']) {
    g.stroke(new Path2D(d))
  }
  g.fillStyle = '#f4f4f4'
  g.beginPath()
  g.arc(12, 12, 3.1, 0, Math.PI * 2)
  g.fill()
  g.restore()
  return c
}

function coinEdge() {
  const [c, g] = canvas(1024, 8)
  for (let x = 0; x < 1024; x += 8) {
    g.fillStyle = '#e0e0e0'
    g.fillRect(x, 0, 4, 8)
    g.fillStyle = '#505050'
    g.fillRect(x + 4, 0, 4, 8)
  }
  return c
}

/** Line boxes, the cited claim and the checked figure, one mask per channel (r, g, b). */
function overlayMasks(lines: Box[], cited: number[], figure: Box, w: number, h: number) {
  const layer = (draw: (g: CanvasRenderingContext2D) => void) => {
    const [, g] = canvas(w, h)
    draw(g)
    return g.getImageData(0, 0, w, h).data
  }
  const rect = (g: CanvasRenderingContext2D, [x0, y0, x1, y1]: Box, pad: number, fill: number, stroke: number) => {
    const x = x0 * w - pad
    const y = y0 * h - pad
    const rw = (x1 - x0) * w + pad * 2
    const rh = (y1 - y0) * h + pad * 2
    g.beginPath()
    g.roundRect(x, y, rw, rh, pad + 2)
    g.fillStyle = `rgba(255,255,255,${fill})`
    g.fill()
    g.lineWidth = stroke
    g.strokeStyle = '#fff'
    g.stroke()
  }
  const k = w / 1754  // stroke widths and padding are designed at 1754 px wide
  const all = layer(g => lines.forEach(box => rect(g, box, 6 * k, 0.16, 3 * k)))
  const claim = layer(g => {
    const boxes = cited.map(i => lines[i])
    const union: Box = [
      Math.min(...boxes.map(b => b[0])), Math.min(...boxes.map(b => b[1])),
      Math.max(...boxes.map(b => b[2])), Math.max(...boxes.map(b => b[3])),
    ]
    rect(g, union, 14 * k, 0.2, 4 * k)
  })
  const fig = layer(g => {
    rect(g, figure, 5 * k, 0.42, 4 * k)
    const [x0, , x1, y1] = figure
    g.fillStyle = '#fff'
    g.fillRect(x0 * w - 5 * k, y1 * h + 9 * k, (x1 - x0) * w + 10 * k, 5 * k)
  })
  const [c, g] = canvas(w, h)
  const out = g.createImageData(w, h)
  for (let i = 0; i < out.data.length; i += 4) {
    out.data[i] = all[i + 3]
    out.data[i + 1] = claim[i + 3]
    out.data[i + 2] = fig[i + 3]
    out.data[i + 3] = 255
  }
  g.putImageData(out, 0, 0)
  return c
}

const OVERLAY_VERT = /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`

const OVERLAY_FRAG = /* glsl */ `
uniform sampler2D map;
uniform float reveal;
uniform float beam;
uniform vec3 layers;
uniform vec3 jade;
uniform vec3 jadeDeep;
uniform vec3 gold;
uniform vec3 beamColor;
varying vec2 vUv;

void over(inout vec3 col, inout float a, vec3 c, float ca) {
  col = c * ca + col * (1.0 - ca);
  a = ca + a * (1.0 - ca);
}

void main() {
  vec3 m = texture2D(map, vUv).rgb;
  float y = 1.0 - vUv.y;
  float shown = 1.0 - smoothstep(reveal - 0.004, reveal + 0.004, y);
  vec3 col = vec3(0.0);
  float a = 0.0;
  over(col, a, jade, m.r * layers.x * shown);
  over(col, a, jadeDeep, m.g * layers.y);
  over(col, a, gold, m.b * layers.z);
  // The scan: a bright line with a short wash above it
  float d = y - reveal;
  float line = exp(-pow(d / 0.0045, 2.0));
  float wash = smoothstep(-0.1, 0.0, d) * step(d, 0.0) * 0.32;
  over(col, a, beamColor, clamp((line + wash) * beam, 0.0, 1.0));
  gl_FragColor = vec4(a > 0.0 ? col / a : col, a);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`

const damp = (from: number, to: number, rate: number, dt: number) => to + (from - to) * Math.exp(-rate * dt)
const rad = THREE.MathUtils.degToRad
const clamp01 = (x: number) => Math.min(1, Math.max(0, x))
const easeOut = (x: number) => 1 - Math.pow(1 - x, 3)
const easeInOut = (x: number) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2)

// The entrance, in seconds from load: the camera settles from overhead while the pages are dealt onto the
// blotter (bottom page first) and the coins drop into their stack.
const INTRO_CAMERA = 2.6
const PAGE_DROP = { delay: 0.2, gap: 0.22, length: 0.85, height: 0.75 }
const COIN_DROP = { delay: 1.15, gap: 0.09, length: 0.45, height: 0.5 }

export function createDesk(opts: DeskOptions): Desk {
  const { canvas: el, host, slot } = opts
  const renderer = new THREE.WebGLRenderer({ canvas: el, antialias: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 0.9
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  const aniso = renderer.capabilities.getMaxAnisotropy()

  const scene = new THREE.Scene()
  scene.background = new THREE.Color('#06110d')
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 120)
  const pmrem = new THREE.PMREMGenerator(renderer)
  const env = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
  const disposables: { dispose: () => void }[] = [pmrem, env]
  const keep = <T extends { dispose: () => void }>(x: T) => (disposables.push(x), x)

  // Light: a lamp straight above the blotter (so the desk beyond it stays dark), a cool jade rim from
  // behind, very little fill. Kept soft enough that the paper is not blown out.
  const lamp = new THREE.SpotLight('#fff6ec', 190, 0, rad(30), 0.8, 1.7)
  lamp.position.set(-0.5, 7.8, 0.5)
  lamp.target.position.set(0.3, 0, 0.2)
  lamp.castShadow = true
  lamp.shadow.mapSize.set(2048, 2048)
  lamp.shadow.bias = -0.0002
  lamp.shadow.normalBias = 0.015
  lamp.shadow.camera.near = 2
  lamp.shadow.camera.far = 20
  scene.add(lamp, lamp.target)
  const rim = new THREE.DirectionalLight('#86e6c2', 0.35)
  rim.position.set(5, 3, -7)
  scene.add(rim)
  scene.add(new THREE.HemisphereLight('#d5ece1', '#04100b', 0.16))

  // The desk: dark lacquer, and on it a leather blotter whose border is tooled in gold.
  const desk = new THREE.Mesh(
    keep(new THREE.PlaneGeometry(80, 80)),
    keep(new THREE.MeshStandardMaterial({ color: '#010302', roughness: 0.92, metalness: 0 })),
  )
  desk.rotation.x = -Math.PI / 2
  desk.receiveShadow = true
  scene.add(desk)

  const grain = leatherGrain()
  const grainTex = keep(new THREE.CanvasTexture(grain))
  const colourTex = keep(new THREE.CanvasTexture(leatherColour(grain)))
  colourTex.colorSpace = THREE.SRGBColorSpace
  const bw = BLOTTER.x1 - BLOTTER.x0
  const bd = BLOTTER.z1 - BLOTTER.z0
  for (const t of [grainTex, colourTex]) {
    t.wrapS = t.wrapT = THREE.RepeatWrapping
    t.repeat.set(bw * 4.2, bd * 4.2)
    t.anisotropy = aniso
  }
  const leather = keep(new THREE.MeshStandardMaterial({ map: colourTex, bumpMap: grainTex, bumpScale: 0.7, roughness: 0.55, metalness: 0 }))
  const leatherEdge = keep(new THREE.MeshStandardMaterial({ color: '#0a2219', roughness: 0.5 }))
  const blotter = new THREE.Mesh(keep(new THREE.BoxGeometry(bw, BLOTTER.h, bd)), [leatherEdge, leatherEdge, leather, leatherEdge, leatherEdge, leatherEdge])
  blotter.position.set((BLOTTER.x0 + BLOTTER.x1) / 2, BLOTTER.h / 2, (BLOTTER.z0 + BLOTTER.z1) / 2)
  blotter.castShadow = blotter.receiveShadow = true
  scene.add(blotter)

  const gold = keep(new THREE.MeshStandardMaterial({ color: '#d29a3c', metalness: 1, roughness: 0.34, envMap: env, envMapIntensity: 0.35 }))
  const rule = (x0: number, z0: number, x1: number, z1: number) => {
    const len = Math.hypot(x1 - x0, z1 - z0)
    const mesh = new THREE.Mesh(keep(new THREE.BoxGeometry(len + 0.018, 0.003, 0.018)), gold)
    mesh.position.set((x0 + x1) / 2, BLOTTER.h + 0.0015, (z0 + z1) / 2)
    mesh.rotation.y = -Math.atan2(z1 - z0, x1 - x0)
    mesh.receiveShadow = true
    scene.add(mesh)
  }
  for (const inset of [0.11, 0.19]) {
    const x0 = BLOTTER.x0 + inset
    const x1 = BLOTTER.x1 - inset
    const z0 = BLOTTER.z0 + inset
    const z1 = BLOTTER.z1 - inset
    rule(x0, z0, x1, z0)
    rule(x1, z0, x1, z1)
    rule(x1, z1, x0, z1)
    rule(x0, z1, x0, z0)
  }

  // Pages: page 4 on top with a lifted corner, pages 6 and 1 underneath.
  const pageH = PAGE_W / opts.aspect
  const lift = (u: number, v: number) => {
    const s = (a: number, b: number, x: number) => {
      const t = clamp01((x - a) / (b - a))
      return t * t * (3 - 2 * t)
    }
    return 0.13 * Math.pow(s(0.55, 1, u) * s(0.45, 1, v), 2) + 0.012 * s(0.2, 0, u)
  }
  const pageGeometry = keep(new THREE.PlaneGeometry(PAGE_W, pageH, 56, 40))
  {
    const pos = pageGeometry.attributes.position
    for (let i = 0; i < pos.count; i++) {
      const u = pos.getX(i) / PAGE_W + 0.5
      const v = 0.5 - pos.getY(i) / pageH
      pos.setZ(i, lift(u, v))
    }
    pageGeometry.computeVertexNormals()
  }
  const flatPage = keep(new THREE.PlaneGeometry(PAGE_W, pageH))
  const loader = new THREE.TextureLoader()
  const loadPage = (src: string) => loader.loadAsync(src).then(t => {
    t.colorSpace = THREE.SRGBColorSpace
    t.anisotropy = aniso
    return keep(t)
  })

  // Bottom page first: each is dealt in with its own drop and a little spin.
  const sheets = [
    { geometry: flatPage, at: [-0.55, BLOTTER.h + 0.003, 0.3], yaw: -11, spin: -14 },
    { geometry: flatPage, at: [0.5, BLOTTER.h + 0.006, -0.36], yaw: 8, spin: 12 },
    { geometry: pageGeometry, at: [0, BLOTTER.h + 0.012, 0], yaw: -4, spin: -9 },
  ].map(({ geometry, at, yaw, spin }) => {
    // Paper a touch below white, so the lamp never blows out the text printed on it
    const material = keep(new THREE.MeshStandardMaterial({ color: '#efede6', roughness: 0.9, transparent: true, opacity: 0 }))
    const mesh = new THREE.Mesh(geometry, material)
    mesh.rotation.set(-Math.PI / 2, 0, rad(yaw))
    mesh.position.set(at[0], at[1], at[2])
    mesh.receiveShadow = true
    scene.add(mesh)
    return { mesh, material, y: at[1], yaw: rad(yaw), spin: rad(spin) }
  })
  const top = sheets[2].mesh

  const maskW = Math.round(1754 * opts.detail)
  const masks = keep(new THREE.CanvasTexture(overlayMasks(opts.lines, opts.cited, opts.figure, maskW, Math.round(maskW / opts.aspect))))
  masks.anisotropy = aniso
  const overlay = keep(new THREE.ShaderMaterial({
    vertexShader: OVERLAY_VERT,
    fragmentShader: OVERLAY_FRAG,
    transparent: true,
    depthWrite: false,
    polygonOffset: true,
    polygonOffsetFactor: -2,
    polygonOffsetUnits: -2,
    uniforms: {
      map: { value: masks },
      reveal: { value: opts.reduced ? SCAN_END : 0 },
      beam: { value: 0 },
      layers: { value: new THREE.Vector3(...LAYERS[0]) },
      jade: { value: new THREE.Color(JADE) },
      jadeDeep: { value: new THREE.Color(JADE_DEEP) },
      gold: { value: new THREE.Color(GOLD) },
      beamColor: { value: new THREE.Color(BEAM) },
    },
  }))
  const overlayMesh = new THREE.Mesh(pageGeometry, overlay)
  overlayMesh.renderOrder = 1
  overlayMesh.visible = false
  top.add(overlayMesh)

  // AuraCoins: a short stack and one loose coin by the page's corner.
  const faceTex = keep(new THREE.CanvasTexture(coinFace()))
  const edgeTex = keep(new THREE.CanvasTexture(coinEdge()))
  edgeTex.wrapS = THREE.RepeatWrapping
  const coinGold = { color: '#d9a443', metalness: 1, roughness: 0.3, envMap: env, envMapIntensity: 1.25 }
  const faceMat = keep(new THREE.MeshStandardMaterial({ ...coinGold, bumpMap: faceTex, bumpScale: 3 }))
  const edgeMat = keep(new THREE.MeshStandardMaterial({ ...coinGold, roughness: 0.36, bumpMap: edgeTex, bumpScale: 1.2 }))
  const coinGeo = keep(new THREE.CylinderGeometry(0.2, 0.2, 0.03, 72))
  const rand = rng(5)
  const coins: { mesh: THREE.Mesh; y: number }[] = []
  const coin = (x: number, y: number, z: number, spin: number) => {
    const mesh = new THREE.Mesh(coinGeo, [edgeMat, faceMat, faceMat])
    const rest = BLOTTER.h + y + 0.015
    mesh.position.set(x, rest, z)
    mesh.rotation.y = spin
    mesh.castShadow = mesh.receiveShadow = true
    mesh.visible = false
    scene.add(mesh)
    coins.push({ mesh, y: rest })
  }
  for (let i = 0; i < 5; i++) coin(2.4 + (rand() - 0.5) * 0.04, i * 0.031, 1.4 + (rand() - 0.5) * 0.04, rand() * 6)
  coin(1.95, 0, 1.82, 0.6)

  const restMatrix = () => {
    const { position, rotation } = top
    const saved = [position.y, rotation.z]
    position.y = sheets[2].y
    rotation.z = sheets[2].yaw
    top.updateMatrixWorld(true)
    const m = top.matrixWorld.clone()
    position.y = saved[0]
    rotation.z = saved[1]
    return m
  }
  const rest = restMatrix()
  // Page points use where page 4 comes to rest, so the camera and callouts don't follow it in mid-air.
  const pagePoint = (u: number, v: number, out = new THREE.Vector3(), raised = true) =>
    out.set((u - 0.5) * PAGE_W, (0.5 - v) * pageH, raised ? lift(u, v) + 0.004 : 0).applyMatrix4(rest)

  // Layout: the canvas covers the host; the page is framed inside the slot.
  const layout = { w: 1, h: 1, cx: 0.5, cy: 0.5, fit: 10 }
  const measure = () => {
    const hr = host.getBoundingClientRect()
    const sr = slot.getBoundingClientRect()
    layout.w = Math.max(1, hr.width)
    layout.h = Math.max(1, hr.height)
    layout.cx = sr.left - hr.left + sr.width / 2
    layout.cy = sr.top - hr.top + sr.height / 2
    renderer.setSize(layout.w, layout.h, false)
    const t = Math.tan(rad(FOV / 2))
    const sw = Math.max(80, sr.width)
    const sh = Math.max(80, sr.height)
    const dW = (PAGE_W * 1.42 * layout.h) / (2 * t * sw)
    const dH = (pageH * Math.sin(rad(BASE_ELEV)) * 1.6 * layout.h) / (2 * t * sh)
    layout.fit = Math.max(dW, dH)
  }
  const resize = new ResizeObserver(measure)
  resize.observe(host)
  resize.observe(slot)
  measure()

  // State
  let step = 0
  let reveal = opts.reduced ? SCAN_END : 0
  let started = 0
  const cam = { ...SHOTS[0] }
  const layers = [...LAYERS[0]]
  let beam = 0
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 }
  const onPointer = (e: PointerEvent) => {
    const r = host.getBoundingClientRect()
    pointer.tx = ((e.clientX - r.left) / r.width) * 2 - 1
    pointer.ty = ((e.clientY - r.top) / r.height) * 2 - 1
  }
  if (!opts.reduced) host.addEventListener('pointermove', onPointer)

  let visible = true
  const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting })
  io.observe(host)

  const target = new THREE.Vector3()
  const scratch = new THREE.Vector3()
  const project = (u: number, v: number): [number, number] => {
    pagePoint(u, v, scratch).project(camera)
    return [((scratch.x + 1) / 2) * layout.w, ((1 - scratch.y) / 2) * layout.h]
  }

  const entrance = (t: number) => {
    sheets.forEach((sheet, i) => {
      const p = clamp01((t - PAGE_DROP.delay - i * PAGE_DROP.gap) / PAGE_DROP.length)
      const e = easeOut(p)
      sheet.mesh.position.y = sheet.y + (1 - e) * PAGE_DROP.height
      sheet.mesh.rotation.z = sheet.yaw + (1 - e) * sheet.spin
      sheet.material.opacity = clamp01(p * 2.5)
      sheet.mesh.castShadow = p > 0.1
      if (p >= 1 && sheet.material.transparent) {
        sheet.material.transparent = false
        sheet.material.needsUpdate = true
      }
    })
    overlayMesh.visible = sheets[2].material.opacity >= 1
    coins.forEach((c, i) => {
      const p = clamp01((t - COIN_DROP.delay - i * COIN_DROP.gap) / COIN_DROP.length)
      c.mesh.visible = p > 0
      c.mesh.position.y = c.y + (1 - easeOut(p)) * COIN_DROP.height
    })
  }

  let raf = 0
  let last = performance.now()
  const frame = (now: number) => {
    raf = requestAnimationFrame(frame)
    if (!visible || document.hidden) {
      // Hold the clock while off screen, so the entrance resumes where it stopped.
      started += now - last
      last = now
      return
    }
    const dt = Math.min(0.05, (now - last) / 1000)
    last = now
    const motion = opts.reduced ? 0 : 1
    const t = motion ? (now - started) / 1000 : 99
    entrance(t)

    const scanning = step === 0 && t >= opts.scanDelay && reveal < SCAN_END
    if (scanning) reveal = Math.min(SCAN_END, reveal + dt / SCAN_SECONDS)
    beam = motion ? damp(beam, scanning ? 1 : 0, 9, dt) : 0
    const shot = SHOTS[step]
    for (const k of ['u', 'v', 'zoom', 'azim', 'elev'] as const) cam[k] = motion ? damp(cam[k], shot[k], 2.4, dt) : shot[k]
    for (let i = 0; i < 3; i++) layers[i] = motion ? damp(layers[i], LAYERS[step][i], 5, dt) : LAYERS[step][i]
    pointer.x = damp(pointer.x, pointer.tx, 3, dt)
    pointer.y = damp(pointer.y, pointer.ty, 3, dt)

    const settle = 1 - easeInOut(clamp01(t / INTRO_CAMERA))
    const drift = motion * Math.sin(t / 5.2) * 1.4
    const elev = rad(BASE_ELEV + cam.elev - pointer.y * 2.2 + settle * 24)
    const azim = rad(BASE_AZIM + cam.azim + pointer.x * 3.2 + drift - settle * 26)
    const dist = (layout.fit / cam.zoom) * (1 + settle * 0.5)
    pagePoint(cam.u, cam.v, target, false)
    camera.position.set(
      target.x + dist * Math.cos(elev) * Math.sin(azim),
      target.y + dist * Math.sin(elev),
      target.z + dist * Math.cos(elev) * Math.cos(azim),
    )
    camera.lookAt(target)
    camera.aspect = layout.w / layout.h
    camera.setViewOffset(layout.w, layout.h, layout.w / 2 - layout.cx, layout.h / 2 - layout.cy, layout.w, layout.h)

    const u = overlay.uniforms
    u.reveal.value = reveal
    u.beam.value = beam
    ;(u.layers.value as THREE.Vector3).set(layers[0], layers[1], layers[2])

    renderer.render(scene, camera)
    opts.onFrame?.({ reveal: Math.min(1, reveal), project, width: layout.w, height: layout.h })
  }

  const ready = Promise.all([loadPage(opts.pages.top), ...opts.pages.under.map(loadPage)]).then(([p4, p6, p1]) => {
    for (const [sheet, map] of [[sheets[0], p1], [sheets[1], p6], [sheets[2], p4]] as const) {
      sheet.material.map = map
      sheet.material.needsUpdate = true
    }
    renderer.compile(scene, camera)
    last = started = performance.now()
    raf = requestAnimationFrame(frame)
  })

  return {
    ready,
    setStep(next) {
      if (next === step) return
      reveal = next === 0 && !opts.reduced ? 0 : SCAN_END
      step = next
    },
    dispose() {
      cancelAnimationFrame(raf)
      resize.disconnect()
      io.disconnect()
      host.removeEventListener('pointermove', onPointer)
      for (const d of disposables) d.dispose()
      renderer.dispose()
    },
  }
}
