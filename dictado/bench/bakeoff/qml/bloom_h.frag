#version 440
// Bloom pass 1 (bake-off v4): umbral de brillo + gaussiana horizontal de 9
// taps sobre la escena. Corre a media resolucion (112x112). El alfa viaja
// junto al color: es lo que el post-proceso del motor Quick3D no hace sobre
// ventana transparente.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float threshold;
    vec2 texel;      // 1/ancho, 1/alto del buffer de entrada
};
layout(binding = 1) uniform sampler2D src;

void main() {
    // Umbral con suavizado: solo lo brillante alimenta el bloom.
    vec4 c = texture(src, qt_TexCoord0);
    float lum = dot(c.rgb, vec3(0.344, 0.5, 0.156));
    float w = smoothstep(threshold, threshold + 0.35, lum);

    // Gaussiana 9 taps (pesos 1,8,28,56,70,56,28,8,1 / 256).
    float weights[5] = float[5](0.2734375, 0.21875, 0.109375, 0.03125, 0.00390625);
    vec4 acc = c * w * weights[0];
    for (int i = 1; i < 5; ++i) {
        vec2 off = vec2(texel.x * float(i) * 2.0, 0.0);
        acc += texture(src, qt_TexCoord0 + off) * w * weights[i];
        acc += texture(src, qt_TexCoord0 - off) * w * weights[i];
    }
    fragColor = acc * qt_Opacity;
}
