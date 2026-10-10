import * as THREE from 'three'

export const INTRO_DURATION_MS = 5200

const ease = (t: number) => t * t * (3 - 2 * t)
const clamp01 = (t: number) => Math.max(0, Math.min(1, t))

function random(seed: number) {
  let value = seed >>> 0
  return () => {
    value += 0x6d2b79f5
    let t = value
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function terrainHeight(x: number, z: number) {
  const d = Math.hypot(x, z + 17)
  const bowl = -2.9 * Math.pow(Math.max(0, 1 - d / 8.3), 1.7)
  const rim = 1.3 * Math.exp(-Math.pow((d - 8.5) / 1.8, 2))
  const undulation = 0.24 * Math.sin(x * 0.33) * Math.cos(z * 0.29) + 0.11 * Math.sin(x * 1.37 + z * 1.21)
  const smaller = -0.34 * Math.exp(-Math.pow(Math.hypot(x + 20, z + 38) / 4, 2))
  return -2.7 + bowl + rim + undulation + smaller
}

function makeTerrain(mobile: boolean) {
  const geometry = new THREE.PlaneGeometry(180, 180, mobile ? 110 : 180, mobile ? 110 : 180)
  geometry.rotateX(-Math.PI / 2)
  const position = geometry.attributes.position
  const colors = new Float32Array(position.count * 3)
  const low = new THREE.Color('#555961')
  const high = new THREE.Color('#93949a')
  const color = new THREE.Color()
  for (let i = 0; i < position.count; i++) {
    const x = position.getX(i)
    const z = position.getZ(i)
    const h = terrainHeight(x, z)
    position.setY(i, h)
    const shade = clamp01(0.42 + h * 0.085 + 0.12 * Math.sin(x * 2.2 + z * 1.7))
    color.copy(low).lerp(high, shade)
    colors[i * 3] = color.r
    colors[i * 3 + 1] = color.g
    colors[i * 3 + 2] = color.b
  }
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  geometry.computeVertexNormals()
  return new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, metalness: 0, side: THREE.DoubleSide }))
}

function makeStars(mobile: boolean) {
  const count = mobile ? 1100 : 2600
  const rand = random(26)
  const positions = new Float32Array(count * 3)
  const colors = new Float32Array(count * 3)
  const sizes = new Float32Array(count)
  for (let i = 0; i < count; i++) {
    const azimuth = rand() * Math.PI * 2
    const altitude = 0.08 + rand() * 1.36
    const radius = 140
    positions.set([radius * Math.cos(altitude) * Math.sin(azimuth), radius * Math.sin(altitude), radius * Math.cos(altitude) * Math.cos(azimuth)], i * 3)
    const warmth = rand()
    colors.set(warmth > 0.88 ? [1, 0.75, 0.52] : warmth > 0.55 ? [0.68, 0.85, 1] : [0.91, 0.94, 1], i * 3)
    sizes[i] = 1.0 + Math.pow(rand(), 10) * 2.6
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  geometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1))
  const material = new THREE.ShaderMaterial({
    uniforms: { alpha: { value: 0 }, pixelRatio: { value: 1 } },
    vertexColors: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    vertexShader: `attribute float size; varying vec3 vColor; uniform float pixelRatio;
      void main(){ vColor = color; vec4 p = modelViewMatrix * vec4(position, 1.0); gl_Position = projectionMatrix * p; gl_PointSize = size * pixelRatio; }`,
    fragmentShader: `varying vec3 vColor; uniform float alpha;
      void main(){ float r = length(gl_PointCoord - vec2(0.5)); float a = smoothstep(0.5, 0.05, r) * alpha; gl_FragColor = vec4(vColor, a); }`,
  })
  const stars = new THREE.Points(geometry, material)
  stars.frustumCulled = false
  return { stars, material }
}

function glowTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const context = canvas.getContext('2d')!
  const gradient = context.createRadialGradient(64, 64, 0, 64, 64, 64)
  gradient.addColorStop(0, 'rgba(255,224,174,0.50)')
  gradient.addColorStop(0.18, 'rgba(218,174,120,0.20)')
  gradient.addColorStop(1, 'rgba(218,174,120,0)')
  context.fillStyle = gradient
  context.fillRect(0, 0, 128, 128)
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

function makeRover() {
  const rover = new THREE.Group()
  const hull = new THREE.MeshStandardMaterial({ color: '#9a9da1', metalness: 0.52, roughness: 0.48 })
  const dark = new THREE.MeshStandardMaterial({ color: '#222b32', metalness: 0.35, roughness: 0.78 })
  const gold = new THREE.MeshStandardMaterial({ color: '#c7a777', metalness: 0.62, roughness: 0.42 })
  const lamp = new THREE.MeshBasicMaterial({ color: '#b8ebff' })
  const body = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.48, 1.25), hull)
  body.position.y = 0.72
  rover.add(body)
  const deck = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.08, 1.0), gold)
  deck.position.y = 1.02
  rover.add(deck)
  for (const side of [-1, 1]) for (const z of [-0.55, 0, 0.55]) {
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.16, 14), dark)
    wheel.rotation.z = Math.PI / 2
    wheel.position.set(side * 1.16, 0.36, z)
    rover.add(wheel)
  }
  const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.05, 0.85, 8), hull)
  mast.position.set(-0.4, 1.46, -0.3)
  rover.add(mast)
  const head = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.24, 0.27), dark)
  head.position.set(-0.4, 1.9, -0.34)
  rover.add(head)
  for (const x of [-0.58, -0.22]) {
    const eye = new THREE.Mesh(new THREE.CircleGeometry(0.065, 16), lamp)
    eye.position.set(x, 1.91, -0.481)
    rover.add(eye)
  }
  rover.position.set(6.2, terrainHeight(6.2, -1.5), -1.5)
  rover.rotation.y = -0.28
  rover.scale.setScalar(0.78)
  return rover
}

export function canUseWebGL(canvas: Pick<HTMLCanvasElement, 'getContext'>): boolean {
  try { return Boolean(canvas.getContext('webgl2')) } catch { return false }
}

export function mountLunarScene(canvas: HTMLCanvasElement): () => void {
  if (!canUseWebGL(canvas)) throw new Error('WebGL 2 is unavailable')
  const context = canvas.getContext('webgl2')
  if (!context) throw new Error('WebGL 2 is unavailable')
  const renderer = new THREE.WebGLRenderer({ canvas, context, antialias: true, powerPreference: 'high-performance' })
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = 0.05
  renderer.setClearColor('#03070c')
  const scene = new THREE.Scene()
  scene.background = new THREE.Color('#03070c')
  scene.fog = new THREE.FogExp2('#03070c', 0.008)
  const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 300)
  const mobile = window.innerWidth < 720
  const terrain = makeTerrain(mobile)
  scene.add(terrain)
  const { stars, material: starMaterial } = makeStars(mobile)
  scene.add(stars)
  const sun = new THREE.DirectionalLight('#fff1d9', 4.2)
  sun.position.set(-24, 34, -38)
  scene.add(sun)
  scene.add(new THREE.HemisphereLight('#768da5', '#171719', 1.35))
  const horizonTexture = glowTexture()
  const horizon = new THREE.Sprite(new THREE.SpriteMaterial({ map: horizonTexture, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0 }))
  horizon.position.set(-25, 8, -65)
  horizon.scale.set(76, 39, 1)
  scene.add(horizon)
  const rover = makeRover()
  scene.add(rover)
  const beacon = new THREE.PointLight('#94dfff', 9, 6)
  beacon.position.set(6.2, terrainHeight(6.2, -1.5) + 1.3, -1.7)
  scene.add(beacon)

  let width = 0
  let height = 0
  let pixelRatio = 0
  const resize = () => {
    const rect = canvas.getBoundingClientRect()
    const nextWidth = Math.max(1, Math.floor(rect.width))
    const nextHeight = Math.max(1, Math.floor(rect.height))
    const nextRatio = Math.min(window.devicePixelRatio || 1, mobile ? 1.25 : 1.6)
    if (nextWidth === width && nextHeight === height && nextRatio === pixelRatio) return
    width = nextWidth; height = nextHeight; pixelRatio = nextRatio
    renderer.setPixelRatio(pixelRatio)
    renderer.setSize(width, height, false)
    camera.aspect = width / height
    camera.updateProjectionMatrix()
    starMaterial.uniforms.pixelRatio.value = pixelRatio
  }
  const observer = new ResizeObserver(resize)
  observer.observe(canvas)
  resize()
  const started = performance.now()
  let disposed = false
  const frame = (time: number) => {
    if (disposed) return
    resize()
    const progress = clamp01((time - started) / INTRO_DURATION_MS)
    const travel = ease(progress)
    const narrow = width < 640
    camera.position.set(
      THREE.MathUtils.lerp(-5, narrow ? 2.4 : 5.8, travel),
      THREE.MathUtils.lerp(14.8, narrow ? 10.2 : 8.1, travel),
      THREE.MathUtils.lerp(37, narrow ? 15.8 : 9.8, travel),
    )
    camera.lookAt(0, -2.0, THREE.MathUtils.lerp(-26, -16, travel))
    starMaterial.uniforms.alpha.value = ease(clamp01(progress / 0.27)) * 0.92
    renderer.toneMappingExposure = 0.08 + 1.36 * ease(clamp01((progress - 0.03) / 0.58))
    ;(horizon.material as THREE.SpriteMaterial).opacity = 0.55 * ease(clamp01((progress - 0.14) / 0.45))
    beacon.intensity = 7 + Math.sin(time * 0.002) * 1.5
    renderer.render(scene, camera)
  }
  renderer.setAnimationLoop(frame)
  return () => {
    disposed = true
    renderer.setAnimationLoop(null)
    observer.disconnect()
    scene.traverse((object) => {
      if (object instanceof THREE.Mesh || object instanceof THREE.Points || object instanceof THREE.Sprite) {
        object.geometry?.dispose()
        const materials = Array.isArray(object.material) ? object.material : [object.material]
        materials.forEach((material) => material.dispose())
      }
    })
    horizonTexture.dispose()
    renderer.dispose()
    renderer.forceContextLoss()
  }
}
