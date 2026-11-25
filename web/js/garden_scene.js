/**
 * garden_scene.js — Three.js scene for the Butterfly Garden.
 * EXACT part: the wing colour. Each butterfly owns a 90×1 DataTexture LUT of display RGB vs angle θ = 0…89°,
 * computed from the thin-film model (physics.buildLUT: Abelès TMM, unpolarised, CIE 1931, chosen illuminant).
 * The fragment shader evaluates θ per pixel = acos|N·V| between the view vector and the (bent) wing normal and
 * samples the LUT. ARTISTIC parts: exposure normalisation (displayRGB), wing outline, veins/scale/margin mask,
 * wing bending, flapping, flight paths, garden, fireflies.
 */
import * as THREE from "three";

export const LUT_SIZE = 90; // θ = 0..89°

const WING_VERT = /* glsl */`
uniform float uBend;
uniform float uTwist;
varying vec3 vN;
varying vec3 vV;
varying vec2 vUv;
void main() {
  vUv = uv;
  vec3 p = position;                          // wing plane: x = root→tip (0..1), z = back→front (-1..1), normal +y
  p.y += uBend * p.x * p.x + uTwist * p.x * p.z;   // artistic flex (gives a spread of view angles across the wing)
  vec3 n = normalize(vec3(-(2.0 * uBend * p.x + uTwist * p.z), 1.0, -(uTwist * p.x)));
  vN = normalize(normalMatrix * n);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vV = -mv.xyz;
  gl_Position = projectionMatrix * mv;
}`;

const WING_FRAG = /* glsl */`
uniform sampler2D uLUT;
uniform sampler2D uLUT2;
uniform float uMix;        // LUT cross-fade (singing)
uniform float uOverride;   // fixed viewing angle in degrees, < 0 = per-pixel physical angle
uniform float uSel;        // selection glow
uniform float uSeed;
uniform float uPattern;    // strength of the artistic mask
varying vec3 vN;
varying vec3 vV;
varying vec2 vUv;
float ell(vec2 p, vec2 c, vec2 r, float a) {
  vec2 d = p - c; float cs = cos(a), sn = sin(a);
  d = vec2(cs * d.x + sn * d.y, -sn * d.x + cs * d.y);
  return dot(d / r, d / r);
}
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7)) + uSeed * 17.0) * 43758.5453); }
void main() {
  float wx = vUv.x;                 // 0 at the body, 1 at the tip
  float fy = -(vUv.y * 2.0 - 1.0);  // + = forward
  vec2 p = vec2(wx, fy);
  float ef = ell(p, vec2(0.50, 0.30), vec2(0.53, 0.28), -0.42);  // forewing
  float eh = ell(p, vec2(0.33, -0.30), vec2(0.37, 0.36), 0.25);  // hindwing
  float e = min(ef, eh);
  if (e > 1.0) discard;
  // ---- physics: angle between view vector and wing normal -> LUT (exact thin-film colour)
  vec3 N = normalize(vN);
  vec3 V = normalize(vV);
  float c = clamp(abs(dot(N, V)), 0.0, 1.0);
  float th = degrees(acos(c));
  if (uOverride >= 0.0) th = uOverride;
  float u = (clamp(th, 0.0, 89.0) + 0.5) / 90.0;
  vec3 col = mix(texture2D(uLUT, vec2(u, 0.5)).rgb, texture2D(uLUT2, vec2(u, 0.5)).rgb, uMix);
  // ---- artistic mask: dark margin, veins, scale rows, root hairs
  float m = 1.0;
  float margin = smoothstep(0.78, 0.97, e);
  m *= 1.0 - 0.85 * margin * uPattern;
  float ang = atan(fy, wx + 0.02);
  float vein = abs(fract(ang * 2.6 + 0.5) - 0.5);
  m *= 1.0 - 0.45 * uPattern * (1.0 - smoothstep(0.0, 0.035, vein)) * smoothstep(0.08, 0.3, length(p));
  m *= 1.0 - 0.06 * uPattern * step(0.5, fract(length(p) * 70.0));
  m *= mix(1.0, 0.25 + 0.75 * smoothstep(0.0, 0.22, length(p)), uPattern);
  float dots = step(0.86, margin) * step(0.93, hash(floor(p * 28.0)));
  vec3 outCol = col * m + dots * 0.5 * uPattern;
  outCol += uSel * 0.18 * smoothstep(0.88, 1.0, e) * vec3(0.7, 0.8, 1.0);
  gl_FragColor = vec4(outCol, 1.0);
}`;

export function makeLUTTexture() {
  const data = new Uint8Array(LUT_SIZE * 4).fill(255);
  const tex = new THREE.DataTexture(data, LUT_SIZE, 1, THREE.RGBAFormat, THREE.UnsignedByteType);
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearFilter;
  tex.wrapS = THREE.ClampToEdgeWrapping;
  tex.colorSpace = THREE.NoColorSpace; // values are already sRGB-encoded display colours (no double gamma)
  tex.needsUpdate = true;
  return tex;
}

/** rgbList: array of [r,g,b] in [0,1] (physics.buildLUT output, 90 entries). */
export function writeLUT(tex, rgbList) {
  const d = tex.image.data;
  for (let i = 0; i < LUT_SIZE; i++) {
    const c = rgbList[Math.min(i, rgbList.length - 1)];
    d[4 * i] = Math.round(255 * c[0]); d[4 * i + 1] = Math.round(255 * c[1]); d[4 * i + 2] = Math.round(255 * c[2]); d[4 * i + 3] = 255;
  }
  tex.needsUpdate = true;
}

let _wingGeo = null;
function wingGeometry() {
  if (_wingGeo) return _wingGeo;
  const g = new THREE.PlaneGeometry(1, 2, 24, 32);
  g.translate(0.5, 0, 0);
  g.rotateX(-Math.PI / 2);
  _wingGeo = g;
  return g;
}

/** Build a butterfly Object3D. Returns {group, material, wings:[right,left], pivots, lut, lut2}. */
export function makeButterflyMesh(seed = 0) {
  const lut = makeLUTTexture(), lut2 = makeLUTTexture();
  const material = new THREE.ShaderMaterial({
    vertexShader: WING_VERT, fragmentShader: WING_FRAG, side: THREE.DoubleSide,
    uniforms: {
      uLUT: { value: lut }, uLUT2: { value: lut2 }, uMix: { value: 0 }, uOverride: { value: -1 },
      uBend: { value: 0.1 }, uTwist: { value: 0.0 }, uSel: { value: 0 }, uSeed: { value: seed % 97 }, uPattern: { value: 1 },
    },
  });
  const group = new THREE.Group();
  const geo = wingGeometry();
  const pivots = [], wings = [];
  for (const side of [1, -1]) {
    const pivot = new THREE.Group();
    const mesh = new THREE.Mesh(geo, material);
    mesh.scale.set(side, 1, 1);
    mesh.position.x = 0.03 * side;
    pivot.add(mesh);
    group.add(pivot);
    pivots.push(pivot); wings.push(mesh);
  }
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x15131c, roughness: 0.6, metalness: 0.1, emissive: 0x0a0812 });
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.045, 0.62, 4, 10), bodyMat);
  body.rotation.x = Math.PI / 2;
  group.add(body);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.065, 12, 10), bodyMat);
  head.position.z = 0.38;
  group.add(head);
  const antMat = new THREE.LineBasicMaterial({ color: 0x55506a });
  for (const s of [1, -1]) {
    const pts = [new THREE.Vector3(0.02 * s, 0.03, 0.42), new THREE.Vector3(0.12 * s, 0.16, 0.62), new THREE.Vector3(0.16 * s, 0.2, 0.7)];
    group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), antMat));
  }
  wings.forEach((w) => { w.userData.pickable = true; });
  body.userData.pickable = true; head.userData.pickable = true;
  return { group, material, wings, pivots, lut, lut2, body };
}

/** Garden environment (ARTISTIC): ground, grass, flowers, fireflies, fog, lights. Returns {update(t)}. */
export function buildGarden(scene, rng) {
  scene.background = new THREE.Color(0x04050a);
  scene.fog = new THREE.FogExp2(0x04050a, 0.035);
  scene.add(new THREE.HemisphereLight(0x8090ff, 0x102010, 0.55));
  const moon = new THREE.DirectionalLight(0xbfd0ff, 0.6);
  moon.position.set(-6, 10, 4);
  scene.add(moon);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(40, 48), new THREE.MeshStandardMaterial({ color: 0x0a120c, roughness: 1 }));
  ground.rotation.x = -Math.PI / 2;
  scene.add(ground);
  // grass blades
  const blades = 2200;
  const bladeGeo = new THREE.ConeGeometry(0.03, 0.5, 3);
  bladeGeo.translate(0, 0.25, 0);
  const grass = new THREE.InstancedMesh(bladeGeo, new THREE.MeshStandardMaterial({ color: 0x1d3b22, roughness: 0.9 }), blades);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler(), s = new THREE.Vector3(), p = new THREE.Vector3();
  for (let i = 0; i < blades; i++) {
    const r = 1.5 + 16 * Math.sqrt(rng.random()), a = rng.random() * Math.PI * 2;
    p.set(r * Math.cos(a), 0, r * Math.sin(a));
    e.set((rng.random() - 0.5) * 0.5, rng.random() * 6.3, (rng.random() - 0.5) * 0.5);
    q.setFromEuler(e);
    const h = 0.5 + rng.random() * 1.4;
    s.set(1, h, 1);
    m.compose(p, q, s);
    grass.setMatrixAt(i, m);
  }
  scene.add(grass);
  // flowers: stems + glowing heads (muted palette, artistic)
  const nf = 70;
  const stemGeo = new THREE.CylinderGeometry(0.012, 0.016, 1, 4);
  stemGeo.translate(0, 0.5, 0);
  const stems = new THREE.InstancedMesh(stemGeo, new THREE.MeshStandardMaterial({ color: 0x24502c }), nf);
  const heads = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(0.11, 1), new THREE.MeshStandardMaterial({ roughness: 0.5, emissiveIntensity: 0.35 }), nf);
  const palette = [0xb2557a, 0xd9a441, 0x8a6fd6, 0xe0e0f0, 0xd46a4a, 0x5b8fd6];
  const col = new THREE.Color();
  for (let i = 0; i < nf; i++) {
    const r = 2 + 10 * Math.sqrt(rng.random()), a = rng.random() * Math.PI * 2;
    const h = 0.5 + rng.random() * 1.3;
    p.set(r * Math.cos(a), 0, r * Math.sin(a));
    m.compose(p, q.identity(), s.set(1, h, 1));
    stems.setMatrixAt(i, m);
    p.y = h;
    m.compose(p, q, s.set(1, 0.7, 1));
    heads.setMatrixAt(i, m);
    heads.setColorAt(i, col.setHex(palette[i % palette.length]).multiplyScalar(0.8));
  }
  heads.material.emissive = new THREE.Color(0x221122);
  scene.add(stems, heads);
  // fireflies
  const nfly = 160;
  const pos = new Float32Array(nfly * 3), base = new Float32Array(nfly * 3);
  for (let i = 0; i < nfly; i++) {
    base[3 * i] = (rng.random() - 0.5) * 24; base[3 * i + 1] = 0.3 + rng.random() * 4.5; base[3 * i + 2] = (rng.random() - 0.5) * 24;
  }
  const flyGeo = new THREE.BufferGeometry();
  flyGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  const flies = new THREE.Points(flyGeo, new THREE.PointsMaterial({ color: 0xfff2a0, size: 0.07, transparent: true, opacity: 0.8,
    blending: THREE.AdditiveBlending, depthWrite: false }));
  scene.add(flies);
  return {
    update(t) {
      for (let i = 0; i < nfly; i++) {
        pos[3 * i] = base[3 * i] + 0.4 * Math.sin(0.3 * t + i);
        pos[3 * i + 1] = base[3 * i + 1] + 0.25 * Math.sin(0.5 * t + 2.1 * i);
        pos[3 * i + 2] = base[3 * i + 2] + 0.4 * Math.cos(0.27 * t + 1.3 * i);
      }
      flyGeo.attributes.position.needsUpdate = true;
      flies.material.opacity = 0.55 + 0.25 * Math.sin(1.7 * t);
    },
  };
}

/** Selection ring (ARTISTIC). */
export function makeRing() {
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.75, 0.012, 6, 64),
    new THREE.MeshBasicMaterial({ color: 0x9fe8ff, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false }));
  ring.rotation.x = Math.PI / 2;
  ring.visible = false;
  return ring;
}
