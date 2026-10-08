#version 440
// Overlay v3 (bake-off ronda 2, lado QML): techo visual.
// Nucleo como blob fluido (fbm con domain warp), doble halo, anillo de onda
// deformado por las 9 bandas, sweep con eco en processing, particulas
// analiticas deterministas (18 embers por hash; identicas en el lado web) y
// aviso calido. Un solo draw call; el texto del aviso lo pone el QML encima.
//
// El cuerpo matematico de las funciones es EL MISMO que el de web/overlay_v3.html
// (WebGL2); solo cambia el preludio (bloque uniform vs uniforms sueltos).
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float level;
    float pitch;
    float timeS;
    float modeIndex;
    float band0;
    float band1;
    float band2;
    float band3;
    float band4;
    float band5;
    float band6;
    float band7;
    float band8;
};

const float PI = 3.14159265359;
const vec2 SCALE = vec2(224.0);
const float RING_R = 78.0;
const vec3 ACCENT = vec3(0.333, 0.835, 0.784);   // #55d5c8
const vec3 WORKING = vec3(0.561, 0.843, 0.910);  // #8fd7e8
const vec3 ICE = vec3(0.749, 0.937, 1.0);        // #bfefff (rim)
const vec3 AMBER = vec3(0.949, 0.765, 0.416);    // #f2c36a

float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), u.x),
               mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), u.x), u.y);
}

float fbm(vec2 p) {
    float v = 0.0;
    float a = 0.5;
    for (int i = 0; i < 4; ++i) {
        v += a * noise(p);
        p = p * 2.03 + 11.7;
        a *= 0.5;
    }
    return v;
}

// Banda interpolada a lo largo del angulo (0..2PI, 9 controles).
float bandAt(float ang) {
    float bands[9] = float[9](band0, band1, band2, band3, band4, band5, band6, band7, band8);
    float pos = ang / (2.0 * PI) * 9.0;
    float i0 = floor(pos);
    float f = pos - i0;
    int a = int(mod(i0, 9.0));
    int b = int(mod(i0 + 1.0, 9.0));
    return mix(bands[a], bands[b], f * f * (3.0 - 2.0 * f));
}

// Particulas: 18 embers deterministas; en listening salen, en processing caen.
vec4 embers(vec2 p, float nucR, float listening, float processing, float level,
            vec3 col) {
    vec4 acc = vec4(0.0);
    float gate = max(listening, processing);
    if (gate < 0.5)
        return acc;
    for (int i = 0; i < 18; ++i) {
        float fi = float(i);
        float h1 = hash21(vec2(fi, 1.7));
        float h2 = hash21(vec2(fi, 9.3));
        float speed = 0.22 + 0.5 * h2;
        float phase = fract(timeS * speed + h1);
        float rStart = nucR + 8.0;
        float rEnd = 98.0;
        float rr = mix(rStart, rEnd, phase);
        if (processing > 0.5)
            rr = mix(rEnd, rStart, phase);
        float ang = h1 * 2.0 * PI + phase * (0.5 + h2);
        vec2 pos = vec2(cos(ang), sin(ang)) * rr;
        float d = length(p - pos);
        float dotMask = smoothstep(2.8, 1.1, d);
        float fade = sin(phase * PI);
        fade *= (listening > 0.5) ? (0.35 + 0.65 * level) : 1.0;
        float a = dotMask * fade * 0.55;
        acc += vec4(col * a, a);
    }
    return acc;
}

void main() {
    vec2 p = (qt_TexCoord0 - vec2(0.5)) * SCALE;
    float r = length(p);
    float ang = atan(p.y, p.x);

    float idle = 1.0 - step(0.5, modeIndex);
    float starting = step(0.5, modeIndex) * (1.0 - step(1.5, modeIndex));
    float listening = step(1.5, modeIndex) * (1.0 - step(2.5, modeIndex));
    float processing = step(2.5, modeIndex) * (1.0 - step(3.5, modeIndex));
    float notice = step(3.5, modeIndex);

    float breath = 0.5 + 0.5 * sin(timeS * 2.0 * PI / 2.8);
    float pulse = 0.5 + 0.5 * sin(timeS * 2.0 * PI / 0.45);
    vec3 voice = mix(ACCENT, WORKING, pitch);
    vec3 base = mix(voice, AMBER, notice * (1.0 - 0.35 * pulse));

    // --- Blob: radio base + fbm con domain warp sobre el angulo ---
    float nucBase = idle * (16.0 + 1.5 * breath)
                  + starting * (18.0 + 4.0 * level)
                  + listening * (24.0 + 8.0 * level)
                  + processing * (22.0 + 3.0 * sin(timeS * 2.0 * PI / 0.9))
                  + notice * (22.0 + 2.0 * pulse);
    vec2 blobP = vec2(cos(ang), sin(ang)) * 1.6 + vec2(0.0, timeS * 0.28);
    float warp = fbm(blobP * 1.7 + fbm(blobP * 2.3) * 1.4);
    float nucR = nucBase * (1.0 + 0.17 * (warp - 0.5) * 2.0)
               * (1.0 + 0.05 * level * listening);
    float nucA = idle * 0.35 + starting * 0.8 + listening * 0.97
               + processing * 0.92 + notice * (0.6 + 0.4 * pulse);

    // Volumen falso: cuerpo con gradiente + rim de color hielo en el borde.
    float body = smoothstep(nucR + 1.0, nucR - 1.0, r);
    float depth = 1.0 - 0.45 * smoothstep(0.0, nucR, r);
    float rim = smoothstep(nucR + 1.6, nucR - 1.6, r) * smoothstep(nucR - 6.0, nucR - 1.0, r);
    vec3 nucCol = mix(base, ICE, notice * 0.0 + 0.55 * rim);

    // --- Doble halo: glow ancho + bloom cercano ---
    float haloR = nucR + 24.0 + 26.0 * max(listening, starting * 0.3) * level;
    float glowA = idle * 0.35 + starting * 0.55 + listening * 0.8
                + processing * 0.65 + notice * 0.95;
    float glow = pow(clamp(1.0 - r / haloR, 0.0, 1.0), 2.4) * glowA;
    float bloomR = nucR + 10.0;
    float bloom = pow(clamp(1.0 - r / bloomR, 0.0, 1.0), 6.0) * glowA;

    vec3 col = nucCol * (glow * 0.85 + bloom * 0.8 + body * depth * nucA * 0.75
                         + rim * nucA * 0.8);
    float alpha = clamp(glow * 0.85 + bloom * 0.8 + body * nucA + rim * nucA, 0.0, 1.0);

    // --- Anillo de onda: r = R + deformacion por bandas; idle = circulo fijo ---
    float ringGate = max(starting, listening);
    float disp = 0.0;
    if (ringGate > 0.5) {
        disp = bandAt(ang - timeS * (0.15 + 0.35 * level)) * (3.0 + 20.0 * max(level, 0.2));
    }
    float ringR = RING_R + disp * ringGate;
    float ringA = idle * 0.12 + starting * 0.35 + listening * (0.5 + 0.4 * level)
                + processing * 0.22 + notice * (0.5 + 0.4 * pulse);
    float ring = smoothstep(1.6, 0.6, abs(r - ringR));
    float ringGlow = smoothstep(5.5, 2.5, abs(r - ringR)) * 0.35;
    vec3 ringCol = mix(voice, AMBER, notice);
    col += ringCol * (ring + ringGlow) * ringA;
    alpha = clamp(alpha + (ring + ringGlow) * ringA, 0.0, 1.0);

    // --- Processing: sweep principal + eco retrasado con opacidad menor ---
    float sweepCenter = mod(timeS * (2.0 * PI / 1.1), 2.0 * PI);
    float halfSpan = 0.5 * (70.0 * PI / 180.0);
    float echoCenter = sweepCenter - 0.55;
    float dMain = ang - sweepCenter;
    dMain = dMain - 2.0 * PI * floor(dMain / (2.0 * PI) + 0.5);
    float dEcho = ang - echoCenter;
    dEcho = dEcho - 2.0 * PI * floor(dEcho / (2.0 * PI) + 0.5);
    float sweepMain = smoothstep(halfSpan + 0.05, halfSpan - 0.05, abs(dMain))
                    * smoothstep(7.0, 6.0, abs(r - RING_R)) * processing;
    float sweepEcho = smoothstep(halfSpan + 0.05, halfSpan - 0.05, abs(dEcho))
                    * smoothstep(5.0, 4.0, abs(r - RING_R)) * processing * 0.45;
    col += WORKING * (sweepMain * 0.95 + sweepEcho * 0.9);
    alpha = clamp(alpha + sweepMain * 0.95 + sweepEcho * 0.9, 0.0, 1.0);

    // --- Particulas ---
    vec4 emb = embers(p, nucR, listening, processing, level, voice);
    col += emb.rgb;
    alpha = clamp(alpha + emb.a, 0.0, 1.0);

    fragColor = vec4(col, alpha) * qt_Opacity;
}
