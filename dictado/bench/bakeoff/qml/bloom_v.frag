#version 440
// Bloom pass 2 (bake-off v4): gaussiana vertical sobre el bloom + composicion
// con la escena, tonemap exponencial y dithering para romper banding. El alfa
// se compone igual que el color: glow con transparencia real.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float strength;
    float exposure;
    vec2 texel;      // 1/ancho, 1/alto del bloom (media resolucion)
};
layout(binding = 1) uniform sampler2D scene;  // escena a resolucion completa
layout(binding = 2) uniform sampler2D bloom;   // bloom pre-blureado en H

float hash12(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

void main() {
    vec4 c = texture(scene, qt_TexCoord0);

    float weights[5] = float[5](0.2734375, 0.21875, 0.109375, 0.03125, 0.00390625);
    vec4 acc = texture(bloom, qt_TexCoord0) * weights[0];
    for (int i = 1; i < 5; ++i) {
        vec2 off = vec2(0.0, texel.y * float(i) * 2.0);
        acc += texture(bloom, qt_TexCoord0 + off) * weights[i];
        acc += texture(bloom, qt_TexCoord0 - off) * weights[i];
    }
    vec4 glow = acc * strength;
    // El glow ya viene premultiplicado; el tonemap exponencial va sobre su
    // rgb (cada canal, saturacion suave) y el alfa queda intacto.
    glow.rgb = vec3(1.0) - exp(-glow.rgb * exposure);

    vec3 col = c.rgb + glow.rgb;
    float alpha = clamp(c.a + glow.a, 0.0, 1.0);
    float dither = (hash12(gl_FragCoord.xy) - 0.5) / 255.0;
    // Clamp a alfa: la salida de Qt Quick es premultiplicada.
    col = clamp(col + dither, 0.0, alpha);

    fragColor = vec4(col, alpha) * qt_Opacity;
}
