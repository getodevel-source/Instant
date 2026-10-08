#version 440
// Overlay v2 (bake-off, lado QML): nucleo con halo, anillo reactivo,
// espectro de 9 arcos, barrido de "processing" y pulso de aviso.
// Todo el dibujo es analitico en un solo draw call; el texto del aviso lo
// pone el QML encima. Coordenadas: cuadrado 200x200, centro (0,0).
//
// Contrato con el QML (nombres = miembros del uniform block, mismos nombres
// de propiedad en el ShaderEffect): level, pitch, timeS, modeIndex,
// band0..band8. Orden del bloque = orden de propiedades.
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
const vec3 ACCENT = vec3(0.333, 0.835, 0.784);   // #55d5c8
const vec3 WORKING = vec3(0.561, 0.843, 0.910);  // #8fd7e8
const vec3 AMBER = vec3(0.949, 0.765, 0.416);    // #f2c36a

void main() {
    vec2 p = (qt_TexCoord0 - vec2(0.5)) * 224.0;
    float r = length(p);
    float ang = atan(p.y, p.x);
    float s = mod(ang + 3.0 * PI, 2.0 * PI);  // 0..2PI

    float bands[9] = float[9](band0, band1, band2, band3, band4,
                              band5, band6, band7, band8);

    float idle = 1.0 - step(0.5, modeIndex);
    float starting = step(0.5, modeIndex) * (1.0 - step(1.5, modeIndex));
    float listening = step(1.5, modeIndex) * (1.0 - step(2.5, modeIndex));
    float processing = step(2.5, modeIndex) * (1.0 - step(3.5, modeIndex));
    float notice = step(3.5, modeIndex);

    float breath = 0.5 + 0.5 * sin(timeS * 2.0 * PI / 2.8);
    float pulse = 0.5 + 0.5 * sin(timeS * 2.0 * PI / 0.45);

    // --- Nucleo ---
    float nucR = idle * (16.0 + 1.5 * breath)
               + starting * (18.0 + 4.0 * level)
               + listening * (24.0 + 8.0 * level)
               + processing * (22.0 + 3.0 * sin(timeS * 2.0 * PI / 0.9))
               + notice * (22.0 + 2.0 * pulse);
    float nucA = idle * 0.35 + starting * 0.75 + listening * 0.95
               + processing * 0.9 + notice * (0.55 + 0.45 * pulse);
    vec3 nucCol = mix(ACCENT, WORKING, pitch);
    nucCol = mix(nucCol, AMBER, notice);

    float haloR = nucR + 22.0 + 22.0 * max(listening, starting * 0.3) * level;
    float glowA = idle * 0.35 + starting * 0.55 + listening * 0.75
                + processing * 0.6 + notice * 0.9;
    float glow = pow(clamp(1.0 - r / haloR, 0.0, 1.0), 2.2) * glowA;
    float core = smoothstep(nucR + 1.0, nucR - 1.0, r) * nucA;

    vec3 col = nucCol * (glow * 0.9 + core);
    float alpha = clamp(glow * 0.85 + core, 0.0, 1.0);

    // --- Anillo principal (r=56) ---
    float ringA = idle * 0.12
                + starting * 0.30
                + listening * (0.40 + 0.45 * level)
                + processing * 0.25
                + notice * (0.45 + 0.45 * pulse);
    float ringW = 1.5 + 2.5 * level * listening;
    float ring = smoothstep(ringW + 1.0, ringW, abs(r - 56.0));
    vec3 ringCol = mix(mix(ACCENT, WORKING, pitch), AMBER, notice);
    col += ringCol * ring * ringA;
    alpha = clamp(alpha + ring * ringA, 0.0, 1.0);

    // --- Espectro de 9 arcos (r=78, trazo 4px, puntas redondas) ---
    float rot = timeS * (0.15 + 0.35 * level);
    float slot = 2.0 * PI / 9.0;
    float specA = listening * 0.85 + starting * 0.25;
    float stroke = smoothstep(4.5, 3.5, abs(r - 78.0));
    float arcs = 0.0;
    float caps = 0.0;
    for (int i = 0; i < 9; ++i) {
        float c = (float(i) + 0.5) * slot;
        float d = s - rot - c;
        d = d - 2.0 * PI * floor(d / (2.0 * PI) + 0.5);
        float halfspan = 0.5 * slot * (0.12 + 0.88 * bands[i]) * 0.85;
        arcs += smoothstep(halfspan + 0.02, halfspan - 0.02, abs(d));
        // Puntas redondas: discos de radio 2 en los extremos del arco.
        float a1 = c + rot + halfspan;
        float a2 = c + rot - halfspan;
        caps = max(caps, smoothstep(4.4, 3.4, length(p - 78.0 * vec2(cos(a1), sin(a1)))));
        caps = max(caps, smoothstep(4.4, 3.4, length(p - 78.0 * vec2(cos(a2), sin(a2)))));
    }
    float specCov = max(clamp(arcs, 0.0, 1.0) * stroke, caps) * specA;
    col += mix(ACCENT, WORKING, pitch) * specCov;
    alpha = clamp(alpha + specCov, 0.0, 1.0);

    // --- Barrido de processing (arco brillante rotando, r=78) ---
    float sweepCenter = mod(timeS * (2.0 * PI / 1.1), 2.0 * PI);
    float dSweep = s - sweepCenter;
    dSweep = dSweep - 2.0 * PI * floor(dSweep / (2.0 * PI) + 0.5);
    float halfSpan = 0.5 * (70.0 * PI / 180.0);
    float sweep = smoothstep(halfSpan + 0.05, halfSpan - 0.05, abs(dSweep))
                * smoothstep(7.0, 6.0, abs(r - 78.0)) * processing;
    col += WORKING * sweep * 0.9;
    alpha = clamp(alpha + sweep * 0.9, 0.0, 1.0);

    fragColor = vec4(col, alpha) * qt_Opacity;
}
