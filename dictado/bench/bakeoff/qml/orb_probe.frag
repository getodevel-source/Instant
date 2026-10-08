#version 440
// Orbe de prueba del bake-off: nucleo con halo, tintado por nivel.
// Convenciones ShaderEffect Qt 6: bloque std140 con qt_Matrix/qt_Opacity
// primero; qt_TexCoord0 llega del vertex shader interno (location 0).
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float level;
    float pitch;
};
void main() {
    vec2 c = qt_TexCoord0 - vec2(0.5);
    float d = length(c) * 2.0;
    float halo = smoothstep(1.0, 0.0, d);
    float core = smoothstep(0.62, 0.30, d);
    vec3 cool = vec3(0.33, 0.84, 0.78);
    vec3 warm = vec3(0.56, 0.84, 0.91);
    vec3 col = mix(cool, warm, level);
    float a = clamp(halo * halo * 0.85 + core, 0.0, 1.0);
    fragColor = vec4(col * a, a) * qt_Opacity;
}
